"""RAG retrieval and answer generation for Abhishek's portfolio assistant."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

import chromadb
from huggingface_hub import InferenceClient
from transformers import pipeline

from config import (
    COLLECTION_NAME,
    ENABLE_LOCAL_LLM,
    HF_MODEL,
    HF_TOKEN,
    LOCAL_LLM_MODEL,
    TOP_K,
    VECTOR_DB_DIR,
)
from ingest import rebuild_vector_db
from ingest import load_embedding_model
from github_projects import summarize_github_projects
from utils.appointment import build_appointment_response, is_appointment_intent


SYSTEM_PROMPT = (
    "You are Abhishek's professional AI portfolio assistant. Answer questions "
    "about Abhishek using only the provided context from his documents. Be clear, "
    "concise, and professional. If the answer is not available in the documents, "
    "say that the information is not available in the provided data. Do not "
    "hallucinate. Do not show source file names in the final answer."
)


_embedding_model = None
_collection = None
_local_generator = None
_profile_cache = None

STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "built",
    "can",
    "does",
    "explain",
    "for",
    "has",
    "have",
    "his",
    "is",
    "me",
    "of",
    "on",
    "or",
    "raj",
    "the",
    "to",
    "what",
    "who",
    "with",
}

AUTOMATION_TERMS = {
    "automation",
    "automate",
    "power",
    "apps",
    "sharepoint",
    "teams",
    "forms",
    "office",
    "apis",
    "api",
    "scraping",
    "digital",
    "transformation",
}


def _log(message: str) -> None:
    print(f"[rag_chain] {message}")


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        try:
            _embedding_model = load_embedding_model()
        except Exception as exc:
            _log(f"Embedding model loading failure: {exc}")
            raise
    return _embedding_model


def get_collection(auto_ingest: bool = True):
    global _collection
    if _collection is not None:
        return _collection

    client = chromadb.PersistentClient(path=VECTOR_DB_DIR)
    try:
        _collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        _log("ChromaDB collection missing.")
        if auto_ingest:
            _log("Attempting one-time auto-ingestion from the data folder.")
            rebuild_vector_db()
            _collection = client.get_collection(COLLECTION_NAME)
        else:
            raise

    return _collection


def retrieve_context(question: str, top_k: int = TOP_K) -> Tuple[str, List[Dict]]:
    model = get_embedding_model()
    collection = get_collection(auto_ingest=True)

    query_embedding = model.encode([question]).tolist()[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    retrieved = []
    context_parts = []
    for index, text in enumerate(documents):
        if not text:
            continue

        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None
        source = metadata.get("file_name", "unknown source")
        page = metadata.get("page_number")
        source_label = f"{source}, page {page}" if page else source

        retrieved.append({"text": text, "metadata": metadata, "distance": distance})
        context_parts.append(f"Source: {source_label}\n{text}")

    _log(f"Number of chunks retrieved: {len(retrieved)}")
    return "\n\n---\n\n".join(context_parts), retrieved


def list_indexed_sources() -> List[str]:
    collection = get_collection(auto_ingest=True)
    results = collection.get(include=["metadatas"])
    sources = []
    for metadata in results.get("metadatas", []):
        source = metadata.get("file_name") if metadata else None
        if source and source not in sources:
            sources.append(source)
    return sources


def _collection_records() -> List[Dict]:
    collection = get_collection(auto_ingest=True)
    results = collection.get(include=["documents", "metadatas"])
    documents = results.get("documents", []) or []
    metadatas = results.get("metadatas", []) or []
    records = []
    for index, text in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        records.append({"text": text or "", "metadata": metadata or {}})
    return records


def _match_value(text: str, patterns: List[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = match.group(1).strip(" .;|")
            value = re.split(r"\n| {2,}", value)[0].strip(" .;|")
            if value:
                return value
    return None


def _build_profile_facts() -> Dict:
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache

    records = _collection_records()
    profile_records = [
        record
        for record in records
        if "abhishek" in record["text"].lower()
        and "current employer" in record["text"].lower()
    ]
    source_records = profile_records or records
    combined = "\n".join(record["text"] for record in source_records)
    sources = []
    for record in source_records:
        source = record["metadata"].get("file_name")
        if source and source not in sources:
            sources.append(source)

    _profile_cache = {
        "full_name": _match_value(combined, [r"Full Name:\s*([^\n]+)", r"^(Abhishek Raj)\b"]),
        "current_role": _match_value(combined, [r"Current Job Role:\s*([^\n]+)"]),
        "current_employer": _match_value(combined, [r"Current Employer:\s*([^\n]+)"]),
        "experience": _match_value(combined, [r"Total Experience:\s*([^\n]+)"]),
        "location": _match_value(combined, [r"Current Location:\s*([^\n]+)"]),
        "python": _match_value(combined, [r"Programming Languages:\s*([^\n]+)"]),
        "ml_ai": _match_value(combined, [r"Machine Learning & AI:\s*([^\n]+)"]),
        "analytics": _match_value(combined, [r"Data Science & Analytics:\s*([^\n]+)"]),
        "cloud_automation": _match_value(combined, [r"Cloud & Automation:\s*([^\n]+)"]),
        "web": _match_value(combined, [r"Web Development & Scripting:\s*([^\n]+)"]),
        "tools": _match_value(combined, [r"Other Tools:\s*([^\n]+)"]),
        "sources": sources,
        "combined_text": combined,
    }
    return _profile_cache


def _direct_profile_answer(question: str) -> Dict | None:
    lowered = question.lower()
    facts = _build_profile_facts()
    sources = facts.get("sources", [])

    asks_company = any(
        phrase in lowered
        for phrase in [
            "company",
            "employer",
            "working now",
            "work now",
            "currently working",
            "current job",
            "current role",
        ]
    )
    if asks_company:
        employer = facts.get("current_employer")
        role = facts.get("current_role")
        if employer and role:
            return {
                "answer": f"Abhishek is currently working at {employer} as a {role}.",
                "sources": sources[:3],
            }
        if employer:
            return {
                "answer": f"Abhishek is currently working at {employer}.",
                "sources": sources[:3],
            }

    if "who is" in lowered or "about abhishek" in lowered:
        name = facts.get("full_name") or "Abhishek Raj"
        details = []
        if facts.get("current_role") and facts.get("current_employer"):
            details.append(
                f"currently works as a {facts['current_role']} at {facts['current_employer']}"
            )
        if facts.get("experience"):
            details.append(f"has {facts['experience']}")
        if facts.get("location"):
            details.append(f"is currently located in {facts['location']}")
        if facts.get("analytics"):
            details.append(f"works across {facts['analytics']}")
        if details:
            return {
                "answer": f"{name} is a professional who " + ", ".join(details) + ".",
                "sources": sources[:3],
            }

    return None


def _direct_book_answer(question: str) -> Dict | None:
    lowered = question.lower()
    if not any(
        phrase in lowered
        for phrase in [
            "the weight i carried alone",
            "book",
            "story",
            "aariv",
            "nivan",
            "written",
            "author",
        ]
    ):
        return None

    records = [
        record
        for record in _collection_records()
        if "the_weight_i_carried_alone" in record["metadata"].get("file_name", "").lower()
    ]
    if not records:
        return None

    return {
        "answer": (
            "The Weight I Carried Alone is Abhishek's personal reflective book. "
            "It reads like a raw, emotional record of survival, grief, silence, healing, "
            "and rebuilding. The opening sections include a dedication, acknowledgements, "
            "and an author's note that frame the book as a testimony of staying alive, "
            "protecting softness, and finding strength after difficult experiences.\n\n"
            "- Tone: intimate, poetic, vulnerable, and resilient.\n"
            "- Core themes: loneliness, family, loss, survival, self-respect, healing, and hope.\n"
            "- Purpose: not sympathy or revenge, but an honest record of still trying and still staying."
        ),
        "sources": [],
    }


def _direct_contact_or_service_answer(question: str) -> Dict | None:
    lowered = question.lower()

    if "linkedin" in lowered:
        return {
            "answer": (
                "You can connect with Abhishek on LinkedIn here:\n\n"
                "- https://www.linkedin.com/in/abhishekraj1305/\n\n"
                "If you want to discuss work, collaboration, or services, I can also help you book a call."
            ),
            "sources": [],
        }

    if "github" in lowered:
        return {
            "answer": (
                "Abhishek's GitHub profile is:\n\n"
                "- https://github.com/abhishekraj1305\n\n"
                "It includes projects across data science, machine learning, MLOps, OCR, object detection, dashboards, scraping, and portfolio work."
            ),
            "sources": [],
        }

    if any(term in lowered for term in ["portrait", "sketch", "drawing", "art", "custom service", "services"]):
        return {
            "answer": (
                "Abhishek offers both tech and creative services.\n\n"
                "- AI, data science, automation, dashboard, and chatbot projects\n"
                "- Custom portraits\n"
                "- Custom sketches\n"
                "- Scribble-style artwork\n"
                "- Digital drawings\n\n"
                "For custom artwork, share the reference photo/details, preferred style, size or format, deadline, and purpose."
            ),
            "sources": [],
        }

    if any(term in lowered for term in ["contact", "connect", "reach", "email"]):
        return {
            "answer": (
                "You can reach Abhishek through:\n\n"
                "- Email: r.abhishek1305@gmail.com\n"
                "- LinkedIn: https://www.linkedin.com/in/abhishekraj1305/\n"
                "- GitHub: https://github.com/abhishekraj1305\n\n"
                "If you want a call, ask me to book one and I will collect the details."
            ),
            "sources": [],
        }

    return None


def _direct_smalltalk_answer(question: str) -> Dict | None:
    lowered = question.lower().strip()
    normalized = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if normalized in {"thanks", "thank you", "thankyou", "thx"} or "thank you" in normalized:
        return {
            "answer": "You're welcome. Happy to help.",
            "sources": [],
        }
    if normalized in {"hi", "hello", "hey", "hii", "good morning", "good evening", "good afternoon"}:
        return {
            "answer": "Hi! I am Abhishek's AI Bot. You can ask me about Abhishek's work, projects, services, book, or booking a call.",
            "sources": [],
        }
    if normalized in {"bye", "goodbye", "see you"}:
        return {
            "answer": "Goodbye. Have a great day.",
            "sources": [],
        }
    if "how are you" in normalized:
        return {
            "answer": "I am doing well and ready to help with anything about Abhishek.",
            "sources": [],
        }
    return None


def _is_document_inventory_question(question: str) -> bool:
    lowered = question.lower()
    return (
        "what documents" in lowered
        or "which documents" in lowered
        or "documents are you using" in lowered
        or "source files" in lowered
    )


def _generate_with_hf(context: str, question: str) -> str | None:
    if not HF_TOKEN:
        _log("HF_TOKEN missing; using retrieval fallback.")
        return None

    try:
        client = InferenceClient(model=HF_MODEL, token=HF_TOKEN)
        response = client.chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Context:\n{context}\n\n"
                        f"Question:\n{question}\n\n"
                        "Answer in 3-6 concise bullet points when useful. "
                        "Do not include source filenames."
                    ),
                },
            ],
            max_tokens=450,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        return content.strip() if content else None
    except Exception as exc:
        _log(f"Hugging Face generation unavailable: {exc}")
        return None


def _generate_with_local_model(context: str, question: str) -> str | None:
    global _local_generator
    if not ENABLE_LOCAL_LLM:
        return None

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Context:\n{context[:3000]}\n\n"
        f"Question:\n{question}\n\n"
        "Answer:"
    )

    try:
        if _local_generator is None:
            _local_generator = pipeline("text-generation", model=LOCAL_LLM_MODEL)
        output = _local_generator(
            prompt,
            max_new_tokens=220,
            temperature=0.2,
            do_sample=False,
            return_full_text=False,
        )
        generated = output[0].get("generated_text", "").strip()
        return generated or None
    except Exception as exc:
        _log(f"Local text generation unavailable: {exc}")
        return None


def _query_terms(question: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9+#.]+", question.lower())
    terms = {word for word in words if len(word) > 2 and word not in STOP_WORDS}
    if "automation" in terms or "automate" in terms:
        terms.update(AUTOMATION_TERMS)
    return terms


def _split_evidence(text: str) -> List[str]:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip(" -:•\t")
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])|;\s+|\s{2,}", line)
        lines.extend(part.strip() for part in parts if part.strip())
    return lines


def _score_evidence(sentence: str, terms: set[str]) -> int:
    lowered = sentence.lower()
    return sum(1 for term in terms if term in lowered)


def _best_evidence(question: str, retrieved: List[Dict], limit: int = 6) -> List[str]:
    terms = _query_terms(question)
    candidates = []

    for item in retrieved:
        for sentence in _split_evidence(item["text"]):
            if len(sentence) < 25:
                continue
            score = _score_evidence(sentence, terms)
            if score:
                candidates.append((score, len(sentence), sentence))

    candidates.sort(key=lambda row: (-row[0], row[1]))

    selected = []
    seen = set()
    for _, _, sentence in candidates:
        normalized = re.sub(r"\W+", " ", sentence.lower()).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        selected.append(sentence)
        if len(selected) >= limit:
            break

    if selected:
        return selected

    fallback = []
    for item in retrieved[:2]:
        fallback.extend(_split_evidence(item["text"])[:2])
    return fallback[:limit]


def _all_retrieved_evidence(retrieved: List[Dict]) -> List[str]:
    evidence = []
    for item in retrieved:
        evidence.extend(_split_evidence(item["text"]))
    return evidence


def _all_indexed_evidence() -> List[str]:
    evidence = []
    for record in _collection_records():
        evidence.extend(_split_evidence(record["text"]))
    return evidence


def _build_automation_answer(evidence: List[str]) -> str:
    bullets = []
    joined = " ".join(evidence)

    if re.search(r"digital transformation specialist", joined, re.I):
        bullets.append(
            "He currently works as a Digital Transformation Specialist, which ties his automation work directly to business process improvement."
        )
    if re.search(r"office 365|sharepoint|teams|power automate|power apps|forms|power pages", joined, re.I):
        bullets.append(
            "His Microsoft 365 automation stack includes SharePoint, Teams, Power Automate, Power Apps, Forms, and Power Pages."
        )
    if re.search(r"api|rest|flask|fastapi", joined, re.I):
        bullets.append(
            "He also uses Python, Flask/FastAPI, REST APIs, and scripting to connect tools and build workflow-oriented solutions."
        )
    if re.search(r"web scraping|data pipeline|excel|power bi", joined, re.I):
        bullets.append(
            "His broader automation experience includes web scraping, Excel/Power BI workflows, and data pipeline-style tasks."
        )
    if re.search(r"chatbot", joined, re.I):
        bullets.append(
            "The documents also mention chatbot development, which fits his automation and GenAI project work."
        )

    if not bullets:
        bullets = evidence[:4]

    return (
        "Abhishek's automation experience is focused on practical digital transformation: reducing manual work, connecting business tools, and building workflow-based solutions.\n\n"
        + "\n".join(f"- {bullet}" for bullet in bullets[:5])
    )


def _build_python_skills_answer(evidence: List[str]) -> str:
    joined = " ".join(evidence)
    bullets = []

    if re.search(r"python\s*\(4 years\)|python", joined, re.I):
        bullets.append("Python programming with about 4 years of experience.")
    if re.search(r"flask|fastapi|rest api", joined, re.I):
        bullets.append("Backend/API development using Flask, FastAPI, and REST APIs.")
    if re.search(r"numpy|pandas|scikit|tensorflow|pytorch|scipy", joined, re.I):
        bullets.append("Data science libraries including NumPy, Pandas, Scikit-learn, TensorFlow, PyTorch, and SciPy.")
    if re.search(r"matplotlib|seaborn|plotly|visualization|visualisation", joined, re.I):
        bullets.append("Data visualization with Matplotlib, Seaborn, Plotly, Power BI, and related analytics tools.")
    if re.search(r"machine learning|genai|nlp|deep learning|model deployment", joined, re.I):
        bullets.append("Machine learning, GenAI/NLP work, and model deployment experience.")
    if re.search(r"web scraping|pipeline|automation|apis", joined, re.I):
        bullets.append("Automation-oriented Python work such as API integrations, web scraping, and data pipelines.")

    if not bullets:
        bullets = evidence[:5]

    return (
        "Abhishek's Python skills are strongest around data, automation, and applied AI.\n\n"
        + "\n".join(f"- {bullet}" for bullet in bullets[:6])
    )


def _build_projects_answer(evidence: List[str]) -> str:
    joined = " ".join(evidence)
    bullets = []

    if re.search(r"daily work management dashboard|work management system", joined, re.I):
        bullets.append(
            "Daily Work Management Dashboard/System: built for workforce productivity, task tracking, operational KPIs, and leadership reporting."
        )
    if re.search(r"hr analytics dashboard|hr data", joined, re.I):
        bullets.append(
            "HR Analytics Dashboard: Power BI dashboard for HR trends, employee insights, and better HR decision-making."
        )
    if re.search(r"e-commerce sales insight", joined, re.I):
        bullets.append(
            "E-commerce Sales Insight Dashboard: analytics dashboard for sales and business performance insights."
        )
    if re.search(r"nlp model|restaurant ratings|1m\\+ reviews", joined, re.I):
        bullets.append(
            "NLP restaurant-rating prediction model: used Python, TensorFlow, and NLTK on 1M+ reviews, with reported 90% accuracy."
        )
    if re.search(r"mlops pipeline|gcp|kubernetes|jenkins", joined, re.I):
        bullets.append(
            "MLOps Pipeline on GCP: CI/CD pipeline for model deployment/versioning using GCP, Kubernetes, and Jenkins."
        )
    if re.search(r"llama 2|chatbots|basic chatbot", joined, re.I):
        bullets.append(
            "AI chatbot projects: built chatbots using Llama 2/AI models, starting from an early Python chatbot project."
        )
    if re.search(r"microsoft graph api|planner|to-do|onedrive|200\\+ employees", joined, re.I):
        bullets.append(
            "Enterprise task automation: Python and Microsoft Graph API workflows for 200+ employees, reducing manual effort by 90%."
        )
    if re.search(r"azure data factory|azure blob|pentaho|data pipelines|etl", joined, re.I):
        bullets.append(
            "Data engineering pipelines: Azure Data Factory, Azure Blob Storage, containers, PDI/ETL, and Python-based data workflows."
        )

    github_summary = summarize_github_projects(limit=10)
    if github_summary:
        bullets.append("Public GitHub repositories include:")
        bullets.extend(github_summary.splitlines())

    if not bullets:
        bullets = evidence[:6]

    normalized = []
    seen = set()
    for bullet in bullets:
        clean = bullet[2:] if bullet.startswith("- ") else bullet
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(clean)

    return "Abhishek has worked on these portfolio and GitHub projects:\n\n" + "\n".join(
        f"- {bullet}" for bullet in normalized[:8]
    )


def _retrieval_fallback_answer(question: str, retrieved: List[Dict]) -> str:
    if not question or not retrieved:
        return "The information is not available in the provided data."

    evidence = _best_evidence(question, retrieved)
    if not evidence:
        return "The information is not available in the provided data."

    return "Based on Abhishek's documents:\n\n" + "\n".join(
        f"- {sentence}" for sentence in evidence[:5]
    )


def answer_question(question: str) -> Dict:
    question = (question or "").strip()
    _log(f"User query received: {question}")

    if not question:
        return {"answer": "Please ask a question about Abhishek.", "sources": []}

    smalltalk_answer = _direct_smalltalk_answer(question)
    if smalltalk_answer:
        _log("Response generated from smalltalk intent.")
        return smalltalk_answer

    if is_appointment_intent(question):
        return {"answer": build_appointment_response(question), "sources": []}

    book_answer = _direct_book_answer(question)
    if book_answer:
        _log("Response generated from book facts.")
        return book_answer

    contact_answer = _direct_contact_or_service_answer(question)
    if contact_answer:
        _log("Response generated from contact/service facts.")
        return contact_answer

    if _is_document_inventory_question(question):
        try:
            sources = list_indexed_sources()
        except Exception as exc:
            _log(f"Could not list indexed sources: {exc}")
            sources = []

        if not sources:
            return {
                "answer": "No indexed documents are available yet. Please run `python ingest.py`.",
                "sources": [],
            }

        return {
            "answer": "I am using these indexed portfolio documents: "
            + ", ".join(sources),
            "sources": sources,
        }

    direct = _direct_profile_answer(question)
    if direct:
        _log("Response generated from profile facts.")
        return direct

    try:
        context, retrieved = retrieve_context(question, TOP_K)
    except Exception as exc:
        _log(f"Retrieval failed: {exc}")
        return {
            "answer": (
                "I could not access the portfolio knowledge base yet. Please run "
                "`python ingest.py` after adding documents to the data folder."
            ),
            "sources": [],
        }

    if not retrieved:
        return {"answer": "The information is not available in the provided data.", "sources": []}

    lowered_question = question.lower()
    evidence = _all_retrieved_evidence(retrieved)
    indexed_evidence = None
    if "automation" in lowered_question or "automate" in lowered_question:
        indexed_evidence = _all_indexed_evidence()
        answer = _build_automation_answer(indexed_evidence)
    elif "python" in lowered_question:
        indexed_evidence = _all_indexed_evidence()
        answer = _build_python_skills_answer(indexed_evidence)
    elif "project" in lowered_question or "built" in lowered_question:
        indexed_evidence = _all_indexed_evidence()
        answer = _build_projects_answer(indexed_evidence)
    else:
        answer = _generate_with_hf(context, question)
        if not answer:
            answer = _generate_with_local_model(context, question)
        if not answer:
            answer = _retrieval_fallback_answer(question, retrieved)

    sources = []
    for item in retrieved:
        source = item["metadata"].get("file_name")
        if source and source not in sources:
            sources.append(source)

    _log("Response generated.")
    return {"answer": answer, "sources": sources}
