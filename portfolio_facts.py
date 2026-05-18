"""Canonical public facts for Abhishek's portfolio assistant."""

PROFILE_SUMMARY = (
    "Abhishek Raj is a Data Engineer, Data Scientist, AI/ML Automation Engineer, "
    "and Power Platform/Digital Transformation specialist based in Gurgaon, Delhi NCR. "
    "He has 2+ years of experience designing Python, SQL, Azure, API-based, and "
    "dashboard-ready data workflows for enterprise reporting and operational systems."
)

CONTACT_FACTS = {
    "email": "r.abhishek1305@gmail.com",
    "phone": "+91 7261078212",
    "github": "https://github.com/abhishekraj1305",
    "linkedin": "https://www.linkedin.com/in/abhishekraj1305/",
    "location": "Gurgaon, Delhi NCR, India",
}

SKILL_GROUPS = {
    "Languages": ["Python", "SQL", "PySpark", "Shell/Bash basics"],
    "Big data and processing": ["Apache Spark", "Spark SQL", "Databricks", "Delta Lake", "Apache Airflow"],
    "Data engineering": [
        "ETL/ELT pipelines",
        "data extraction",
        "transformation",
        "data validation",
        "batch processing",
        "incremental loading",
        "API integration",
        "logging and monitoring",
        "data modeling",
    ],
    "Warehouse concepts": ["CDC", "Medallion Architecture", "Bronze/Silver/Gold layers", "SCD Type 2", "idempotent pipelines"],
    "Cloud and data services": [
        "Azure Data Factory",
        "Azure Blob Storage",
        "Azure Data Lake Storage",
        "Azure VMs",
        "Azure SQL Database",
        "SQL Server",
        "Snowflake",
        "MongoDB",
    ],
    "Workflow and integration": ["Pentaho Data Integration", "Microsoft Graph API", "Office 365 APIs", "REST APIs", "task scheduling"],
    "Tools": ["Git", "VS Code", "Jira", "Power BI", "Power Apps", "Power Automate"],
}

EXPERIENCE_FACTS = [
    {
        "role": "Data Engineer",
        "org": "Jay Switches Pvt. Ltd.",
        "period": "Feb 2025 - present",
        "facts": [
            "Built ETL pipelines with Python, SQL, Pentaho PDI, and Microsoft Graph API.",
            "Consolidated Planner, To-Do, OneDrive, and Excel task data for 200+ employees.",
            "Reduced manual effort by 90% and improved reporting accuracy by 85%.",
            "Implemented overdue-task alerting and monitoring, increasing task closure rate by 30%.",
        ],
    },
    {
        "role": "Data Engineer",
        "org": "AiToXr Pvt. Ltd.",
        "period": "Jul 2023 - Jan 2025",
        "facts": [
            "Designed Python and Azure VM ingestion pipelines for 160+ global web sources.",
            "Built Azure Data Factory and Azure Blob Storage batch ETL workflows.",
            "Reduced manual intervention by 95% and supported 95% uptime.",
            "Led a team of 3 on validation and error-handling mechanisms.",
        ],
    },
    {
        "role": "Data Engineer Intern",
        "org": "Data Knob",
        "period": "Apr 2023 - Jun 2023",
        "facts": [
            "Built a Python extraction pipeline with BeautifulSoup and Requests for 100,000+ real-estate records.",
            "Cleaned, transformed, structured, and validated datasets for analytics and reporting.",
            "Improved data accuracy to 88% and contributed to a $5,000 revenue impact.",
        ],
    },
]

PROJECT_FACTS = [
    {
        "name": "Medallion Architecture Data Pipeline using PySpark",
        "facts": [
            "Built Bronze, Silver, and Gold layers using PySpark and Delta Lake.",
            "Implemented incremental loading and SCD Type 2 historical tracking.",
            "Used Apache Airflow-style orchestration plus validation and logging mechanisms.",
        ],
    },
    {
        "name": "End-to-End Azure Data Pipeline",
        "facts": [
            "Designed a batch ETL workflow with Azure Data Factory, Azure Blob Storage, and SQL Server.",
            "Ingested and processed structured data into reporting-ready storage layers.",
            "Added validation checks and automated scheduling for reliable data flow.",
        ],
    },
    {
        "name": "Microsoft Graph API Task-Data ETL",
        "facts": [
            "Extracted Planner, To-Do, OneDrive, and Excel task data for 200+ employees.",
            "Used Python, SQL, Pentaho PDI, and Microsoft Graph API.",
            "Reduced manual effort by 90%, improved reporting accuracy by 85%, and supported overdue-task alerting.",
        ],
    },
    {
        "name": "Azure/Python Global Source Ingestion",
        "facts": [
            "Extracted structured data from 160+ global web sources using Python and Azure VMs.",
            "Used Azure Data Factory and Azure Blob Storage for batch processing.",
            "Reduced manual intervention by 95% and supported 95% pipeline uptime.",
        ],
    },
    {
        "name": "NLP restaurant rating prediction",
        "facts": [
            "Public repo frames the project as an NLP workflow on 20K+ reviews with about 85% accuracy per README.",
            "Use this as project evidence, not a production benchmark.",
        ],
    },
]


def bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def data_engineering_answer() -> str:
    return (
        "Abhishek's data engineering experience is strongest in Python, SQL, Azure, APIs, and operational reporting pipelines.\n\n"
        "- Built Python/SQL/Pentaho/Microsoft Graph API ETL for Planner, To-Do, OneDrive, and Excel data across 200+ employees.\n"
        "- Designed Azure/Python ingestion for 160+ global web sources using Azure VMs, Azure Blob Storage, and Azure Data Factory.\n"
        "- Works with ETL/ELT, batch processing, incremental loading, validation, logging, monitoring, and dashboard-ready data modeling.\n"
        "- Is building deeper warehouse capability in PySpark, Databricks, Delta Lake, Airflow, Medallion Architecture, CDC, SCD Type 2, and idempotent pipelines."
    )


def warehousing_answer() -> str:
    return (
        "For data warehousing, Abhishek's portfolio now emphasizes practical pipeline architecture rather than only dashboard output.\n\n"
        "- Medallion Architecture: Bronze raw layer, Silver cleaned/conformed layer, and Gold reporting-ready layer.\n"
        "- PySpark/Spark SQL and Delta Lake for scalable transformation and storage patterns.\n"
        "- Incremental loading, CDC thinking, and SCD Type 2 for historical tracking.\n"
        "- Airflow-style orchestration, validation checks, logging, monitoring, and idempotent pipeline design.\n"
        "- Azure serving paths through Data Factory, Blob/ADLS, SQL Server, Azure SQL, and Power BI-ready models."
    )


def projects_answer() -> str:
    lines = []
    for project in PROJECT_FACTS[:4]:
        lines.append(f"{project['name']}: " + " ".join(project["facts"]))
    return "Abhishek's strongest data engineering projects are:\n\n" + bullet_list(lines)


def skills_answer() -> str:
    groups = []
    for group, skills in SKILL_GROUPS.items():
        groups.append(f"{group}: {', '.join(skills)}")
    return "Abhishek's skills by category:\n\n" + bullet_list(groups)
