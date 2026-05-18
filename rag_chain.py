"""RAG retrieval and answer generation for Abhishek's portfolio assistant."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from config import (
    COLLECTION_NAME,
    ENABLE_HF_GENERATION,
    ENABLE_LOCAL_LLM,
    HF_MODEL,
    HF_TOKEN,
    LOCAL_LLM_MODEL,
    RETRIEVAL_BACKEND,
    TOP_K,
    VECTOR_DB_DIR,
)
from github_projects import summarize_github_projects
from portfolio_facts import (
    CONTACT_FACTS,
    EXPERIENCE_FACTS,
    PROFILE_SUMMARY,
    PROJECT_FACTS,
    data_engineering_answer,
    projects_answer as curated_projects_answer,
    skills_answer as curated_skills_answer,
    warehousing_answer,
)
from utils.appointment import build_appointment_response, is_appointment_intent
from vectorless_store import (
    collection_records as vectorless_records,
    list_sources as vectorless_sources,
    retrieve as vectorless_retrieve,
)


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
    "pricing",
    "price",
    "cost",
    "custom",
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

DATA_ENGINEERING_TERMS = {
    "data engineer",
    "data engineering",
    "warehouse",
    "warehousing",
    "etl",
    "elt",
    "pipeline",
    "pipelines",
    "pyspark",
    "spark",
    "databricks",
    "delta",
    "lake",
    "airflow",
    "medallion",
    "bronze",
    "silver",
    "gold",
    "cdc",
    "scd",
    "azure",
    "adf",
    "blob",
    "adls",
    "sql server",
    "snowflake",
}

UNSUPPORTED_TERMS = {
    "pricing",
    "price",
    "cost",
    "charges",
    "rate",
    "salary",
    "ctc",
    "availability calendar",
}


def _log(message: str) -> None:
    print(f"[rag_chain] {message}")


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        try:
            from ingest import load_embedding_model

            _embedding_model = load_embedding_model()
        except Exception as exc:
            _log(f"Embedding model loading failure: {exc}")
            raise
    return _embedding_model


def get_collection(auto_ingest: bool = True):
    global _collection
    if _collection is not None:
        return _collection

    import chromadb

    client = chromadb.PersistentClient(path=VECTOR_DB_DIR)
    try:
        _collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        _log("ChromaDB collection missing.")
        if auto_ingest:
            from ingest import rebuild_vector_db

            _log("Attempting one-time auto-ingestion from the data folder.")
            rebuild_vector_db()
            _collection = client.get_collection(COLLECTION_NAME)
        else:
            raise

    return _collection


def retrieve_context(question: str, top_k: int = TOP_K) -> Tuple[str, List[Dict]]:
    if RETRIEVAL_BACKEND != "chroma":
        context, retrieved = vectorless_retrieve(question, top_k)
        _log(f"Number of vectorless chunks retrieved: {len(retrieved)}")
        return context, retrieved

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
    if RETRIEVAL_BACKEND != "chroma":
        return vectorless_sources()

    collection = get_collection(auto_ingest=True)
    results = collection.get(include=["metadatas"])
    sources = []
    for metadata in results.get("metadatas", []):
        source = metadata.get("file_name") if metadata else None
        if source and source not in sources:
            sources.append(source)
    return sources


def _collection_records() -> List[Dict]:
    if RETRIEVAL_BACKEND != "chroma":
        return vectorless_records()

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
            "chapter",
            "letter",
            "baba",
            "younger self",
            "future wife",
            "future partner",
            "universe",
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

    section_key = _requested_book_section(question)
    if section_key:
        section_answer = _book_section_answer(section_key, records)
        if section_answer:
            return {"answer": section_answer, "sources": []}

    chapter_number = _requested_book_chapter(question)
    if chapter_number:
        chapter_answer = _book_chapter_answer(chapter_number, records)
        if chapter_answer:
            return {"answer": chapter_answer, "sources": []}

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


def _requested_book_chapter(question: str) -> int | None:
    lowered = question.lower()
    match = re.search(r"\bchapter\s*(\d{1,2})\b", lowered)
    if match:
        return int(match.group(1))

    word_numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
        "twenty": 20,
    }
    for word, number in word_numbers.items():
        if re.search(rf"\bchapter\s+{word}\b", lowered):
            return number
    return None


def _requested_book_section(question: str) -> str | None:
    lowered = question.lower()
    section_aliases = {
        "letter_to_baba": [
            "letter to baba",
            "letter 1",
            "baba letter",
            "to baba",
        ],
        "letter_to_younger_self": [
            "letter to my younger self",
            "younger self",
            "letter 2",
        ],
        "letter_to_whoever_needs_this": [
            "whoever needs this",
            "letter 3",
        ],
        "letter_to_future_partner": [
            "future wife",
            "future partner",
            "letter to my future wife",
            "letter to my future partner",
        ],
        "letter_to_universe": [
            "letter to the universe",
            "unanswered prayer",
            "unanswered prayers",
            "universe",
        ],
    }
    for section_key, aliases in section_aliases.items():
        if any(alias in lowered for alias in aliases):
            return section_key
    return None


def _book_text(records: List[Dict]) -> str:
    return "\n".join(record["text"] for record in records)


def _clean_book_title(title: str) -> str:
    title = (
        title.replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    title = re.sub(r"^Letter\s+\d+\s*-\s*", "", title, flags=re.I)
    return re.sub(r"\s+", " ", title).strip(" .")


def _book_evidence(body: str, limit: int = 5) -> List[str]:
    evidence = []
    seen = set()
    for sentence in _split_evidence(body):
        cleaned = re.sub(r"\s+", " ", sentence).strip()
        normalized = re.sub(r"\W+", " ", cleaned.lower()).strip()
        if len(cleaned) < 35 or normalized in seen:
            continue
        seen.add(normalized)
        evidence.append(cleaned)
        if len(evidence) >= limit:
            break
    return evidence


def _summarize_book_section(title: str, body: str, section_label: str) -> str:
    title = _clean_book_title(title)
    lowered_title = title.lower()

    if "quiet grind" in lowered_title or "self" in lowered_title and "discipline" in lowered_title:
        return (
            f"{section_label}, **{title}**, is about choosing self-discipline as a way to rebuild after chaos, panic, loss, and numbness. "
            "It frames discipline less as productivity aesthetics and more as survival, self-respect, and daily structure.\n\n"
            "- The chapter says motivation is temporary, while discipline is what keeps a person moving after motivation fades.\n"
            "- It connects structure with healing: small habits become a way to stop trauma from deciding the future.\n"
            "- The emotional center is simple but strong: keep showing up even when there is no applause, witness, or celebration."
        )

    if "walking alone with panic" in lowered_title:
        return (
            f"{section_label}, **{title}**, is about carrying panic privately while still trying to function in ordinary life. "
            "It focuses on the loneliness of anxiety, the body-level heaviness of fear, and the effort it takes to keep moving when the mind feels unsafe.\n\n"
            "- The chapter treats panic as something lived through quietly, not as a dramatic scene.\n"
            "- It shows the narrator learning to survive one moment at a time instead of pretending everything is fine.\n"
            "- The emotional movement is from isolation toward the belief that surviving the night still counts as strength."
        )

    if "bruises before i understood hurt" in lowered_title:
        return (
            f"{section_label}, **{title}**, is about childhood pain before a child has the words to name it. "
            "It explains how early fear, unsafe attention, and silent trauma can turn innocence into caution and survival instinct.\n\n"
            "- The chapter shows a child sensing that something is wrong before understanding trauma, boundaries, or betrayal.\n"
            "- It frames inner wounds as marks that later appear as alertness, reserve, mistrust, and shrinking oneself to stay safe.\n"
            "- The emotional movement is from confusion and fear toward adult recognition: the narrator no longer blames the child-self, but honors him for surviving."
        )

    if "to baba" in lowered_title:
        return (
            f"{section_label}, **{title}**, is a grief-and-gratitude letter to Baba. "
            "It remembers him through small daily details, his steadiness, and the narrator's wish to become someone he would be proud of.\n\n"
            "- The letter says Baba's presence still lives in quiet memories, habits, kindness, patience, and empathy.\n"
            "- It carries regret that the narrator could not save him, but also the feeling that Baba's lessons still guide him.\n"
            "- The emotional shift is from missing Baba as pure loss to carrying him as strength and direction."
        )

    evidence = _book_evidence(body, limit=4)
    if evidence:
        return (
            f"{section_label}, **{title}**, focuses on these ideas:\n\n"
            + "\n".join(f"- {sentence}" for sentence in evidence)
        )

    return f"{section_label} is titled **{title}**, but I do not have enough clean text to summarize it reliably."


def _book_section_answer(section_key: str, records: List[Dict]) -> str | None:
    combined = _book_text(records)
    section_patterns = {
        "letter_to_baba": (
            r"(Letter\s+1\s*[—–-]\s*To Baba)(.*?)(?=\n\s*Letter\s+2\s*[—–-]|\Z)",
            "Letter 1",
        ),
        "letter_to_younger_self": (
            r"(Letter\s+2\s*[—–-]\s*To My Younger Self)(.*?)(?=\n\s*Letter\s+3\s*[—–-]|\Z)",
            "Letter 2",
        ),
        "letter_to_whoever_needs_this": (
            r"(Letter\s+3\s*[—–-]\s*To Whoever Needs This)(.*?)(?=\n\s*Letter to My Future Wife|\Z)",
            "Letter 3",
        ),
        "letter_to_future_partner": (
            r"(Letter to My Future Wife\s*/\s*Partner)(.*?)(?=\n\s*Letter to the Universe|\Z)",
            "Letter",
        ),
        "letter_to_universe": (
            r"(Letter to the Universe\s*[—–-]\s*For Every Prayer That Went Unanswered)(.*?)(?=\Z)",
            "Letter",
        ),
    }
    pattern_config = section_patterns.get(section_key)
    if not pattern_config:
        return None

    pattern, section_label = pattern_config
    match = re.search(pattern, combined, re.I | re.S)
    if not match:
        return None
    return _summarize_book_section(match.group(1), match.group(2), section_label)


def _book_chapter_answer(chapter_number: int, records: List[Dict]) -> str | None:
    combined = _book_text(records)
    pattern = rf"Chapter\s+{chapter_number}\s*:\s*([^\n]+)(.*?)(?=\n\s*Chapter\s+\d+\s*:|\Z)"
    match = re.search(pattern, combined, re.I | re.S)
    if not match:
        return f"I could not find Chapter {chapter_number} in the indexed book text. I can answer chapters that are present in the current document, such as chapters 1-29."

    title = _clean_book_title(match.group(1))
    body = match.group(2)
    return _summarize_book_section(title, body, f"Chapter {chapter_number}")


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
                f"- Email: {CONTACT_FACTS['email']}\n"
                f"- Phone: {CONTACT_FACTS['phone']}\n"
                f"- LinkedIn: {CONTACT_FACTS['linkedin']}\n"
                f"- GitHub: {CONTACT_FACTS['github']}\n\n"
                "If you want a call, ask me to book one and I will collect the details."
            ),
            "sources": [],
        }

    return None


def _direct_curated_answer(question: str) -> Dict | None:
    lowered = question.lower()

    if any(term in lowered for term in UNSUPPORTED_TERMS):
        return {
            "answer": (
                "I do not have verified pricing, salary, or commercial-rate information in Abhishek's public portfolio data. "
                "For a project discussion, you can contact Abhishek directly or ask me to book a call."
            ),
            "sources": [],
        }

    if any(phrase in lowered for phrase in ["who is", "about abhishek", "profile", "summary"]):
        return {"answer": PROFILE_SUMMARY, "sources": []}

    if any(term in lowered for term in DATA_ENGINEERING_TERMS):
        if any(term in lowered for term in ["warehouse", "warehousing", "medallion", "bronze", "silver", "gold", "delta", "cdc", "scd"]):
            return {"answer": warehousing_answer(), "sources": []}
        return {"answer": data_engineering_answer(), "sources": []}

    if "azure" in lowered:
        return {
            "answer": (
                "Abhishek's Azure experience includes Azure Data Factory, Azure Blob Storage, Azure Data Lake Storage, Azure VMs, "
                "Azure SQL-style reporting paths, and batch ETL workflows. At AiToXr, he used Python with Azure VMs for 160+ global "
                "sources and Azure Data Factory/Blob Storage for batch processing that reduced manual intervention by 95%."
            ),
            "sources": [],
        }

    if any(term in lowered for term in ["skill", "stack", "tools", "technologies"]):
        return {"answer": curated_skills_answer(), "sources": []}

    if any(term in lowered for term in ["experience", "worked", "career", "job"]):
        bullets = []
        for role in EXPERIENCE_FACTS:
            bullets.append(f"{role['role']} at {role['org']} ({role['period']}): " + " ".join(role["facts"]))
        return {"answer": "Abhishek's experience summary:\n\n" + "\n".join(f"- {item}" for item in bullets), "sources": []}

    if any(term in lowered for term in ["project", "built", "case study", "portfolio"]):
        if "zomato" in lowered or "restaurant" in lowered or "nlp" in lowered:
            project = next((item for item in PROJECT_FACTS if "NLP restaurant" in item["name"]), None)
            if project:
                return {"answer": project["name"] + ":\n\n" + "\n".join(f"- {fact}" for fact in project["facts"]), "sources": []}
        return {"answer": curated_projects_answer(), "sources": []}

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
    if not ENABLE_HF_GENERATION:
        return None

    if not HF_TOKEN:
        _log("HF_TOKEN missing; using retrieval fallback.")
        return None

    try:
        from huggingface_hub import InferenceClient

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
            from transformers import pipeline

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
            "NLP restaurant-rating prediction model: public repo frames the project around 20K+ reviews with about 85% accuracy per README."
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

    terms = _query_terms(question)
    evidence_text = " ".join(evidence).lower()
    matched_terms = {term for term in terms if term in evidence_text}
    if len(terms) >= 2 and len(matched_terms) < 2:
        return (
            "I do not have enough verified information in Abhishek's public portfolio data to answer that accurately. "
            "You can ask about his data engineering work, Azure pipelines, PySpark/Medallion projects, automation, skills, contact details, or booking a call."
        )

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

    curated_answer = _direct_curated_answer(question)
    if curated_answer:
        _log("Response generated from curated portfolio facts.")
        return curated_answer

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
