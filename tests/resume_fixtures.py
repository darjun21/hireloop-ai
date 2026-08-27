"""Representative resume text fixtures for Profile Agent tests (Part J)."""

WELL_STRUCTURED_ENGINEER = """\
Jane Doe
Experienced backend engineer with a focus on distributed systems.

SKILLS
Python, PostgreSQL, AWS, Docker

WORK EXPERIENCE
Senior Backend Engineer | Acme Inc. | 2019-01 - 2022-06
Built and operated production services handling millions of requests using Python and PostgreSQL.

Backend Engineer | Beta Corp | 2016-06 - 2019-01
Developed internal tooling in Python and deployed on AWS.

EDUCATION
B.S. Computer Science | State University | 2012-09 - 2016-05

PROJECTS
Realtime Analytics Pipeline
Built a streaming analytics pipeline using Kafka and Python for internal reporting.

CERTIFICATIONS
AWS Certified Solutions Architect | Amazon | 2021
"""

# B: explicit "Python, LangChain, AWS" skill set to verify extraction.
LANGCHAIN_SKILLS = """\
Priya Shah
AI engineer building retrieval-augmented systems.

SKILLS
Python, LangChain, AWS

WORK EXPERIENCE
AI Engineer | Nova Labs | 2022-01 - Present
Built retrieval pipelines using Python and LangChain deployed on AWS.
"""

# C: no Kubernetes mentioned anywhere, even though the role is AI-adjacent.
NO_KUBERNETES = """\
Sam Lee
Machine learning engineer.

SKILLS
Python, TensorFlow

WORK EXPERIENCE
ML Engineer | DataCo | 2020-01 - 2023-01
Trained and deployed models using Python and TensorFlow.
"""

# D: overlapping employment dates -- two jobs run concurrently for a stretch.
OVERLAPPING_DATES = """\
Alex Kim
Engineering leader with parallel consulting work.

SKILLS
Python, SQL

WORK EXPERIENCE
Staff Engineer | MegaCorp | 2018-01 - 2022-01
Led backend architecture using Python and SQL.

Consulting Engineer | Freelance | 2019-01 - 2021-01
Advised startups on backend architecture using Python.
"""

# E: an unclear certification line that doesn't match "Name | Issuer | Date".
UNCLEAR_CERTIFICATION = """\
Morgan Diaz
Cloud engineer.

SKILLS
Python, AWS

WORK EXPERIENCE
Cloud Engineer | CloudWorks | 2021-01 - 2023-01
Operated cloud infrastructure using Python and AWS.

CERTIFICATIONS
Completed an advanced cloud certification program (details unclear)
"""

# F: a skill (Kafka) that appears only inside a project, not the skills list
# or any work experience.
SKILL_ONLY_IN_PROJECT = """\
Riley Chen
Backend engineer.

SKILLS
Python, PostgreSQL

WORK EXPERIENCE
Backend Engineer | Acme Inc. | 2020-01 - 2023-01
Built services using Python and PostgreSQL.

PROJECTS
Event Streaming Pipeline
Used Kafka and Python to process high-volume event streams for a side project.
"""

# G: skill aliases in the raw skills list.
# AWS is listed only in the Skills line, never mentioned in a work
# experience or project description -- deliberately skills-only evidence
# for Phase 4 Truth Guard "skills-only + strong verb" testing.
AWS_SKILLS_ONLY = """\
Jane Doe
Software engineer.

SKILLS
Python, AWS

WORK EXPERIENCE
Software Engineer | Acme | 2020-01 - 2023-01
Built internal tools using Python.
"""

SKILL_ALIASES_RESUME = """\
Jordan Park
Full-stack engineer.

SKILLS
Postgres, JS, K8s

WORK EXPERIENCE
Full-Stack Engineer | Acme Inc. | 2020-01 - 2023-01
Worked across the stack using Postgres, JS, and K8s.
"""
