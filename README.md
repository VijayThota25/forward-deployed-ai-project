# Cloud Cost Optimizer

A production-style cloud cost optimization platform built with Python, FastAPI, Streamlit, and SQLite. This project analyzes cloud resources, identifies cost-saving opportunities, estimates monthly savings, and generates AWS CLI remediation commands for infrastructure optimization.

## Features

- Analyze cloud resources and utilization
- Detect idle and underutilized resources
- Generate cloud cost optimization recommendations
- Estimate monthly cost savings
- Generate AWS CLI remediation commands
- Interactive Streamlit dashboard
- REST APIs using FastAPI
- SQLite sample database
- Automated testing with Pytest

## Technology Stack

- Python
- FastAPI
- Streamlit
- SQLite
- SQLAlchemy
- Pydantic
- Pytest
- AWS CLI

## Project Structure

```text
app/
dashboard/
data/
scripts/
tests/
README.md
requirements.txt
pytest.ini
```

## Installation

### Clone the repository

```bash
git clone https://github.com/VijayThota25/forward-deployed-ai-project.git
cd forward-deployed-ai-project
```

### Create a virtual environment

```bash
python -m venv .venv
```

### Activate the environment

Windows:

```powershell
.venv\Scripts\Activate.ps1
```

### Install dependencies

```bash
pip install -r requirements.txt
```

## Run the API

```bash
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Run the Dashboard

```bash
streamlit run dashboard/app.py
```

Open:

```text
http://localhost:8501
```

## Run Tests

```bash
pytest
```

## Sample Use Cases

- Detect idle EC2 instances
- Identify oversized cloud resources
- Find unattached EBS volumes
- Identify unused Elastic IPs
- Generate AWS CLI remediation commands
- Estimate monthly cloud cost savings

## Future Enhancements

- Multi-cloud support
- AI-powered optimization recommendations
- Cost anomaly detection
- Docker deployment
- CI/CD with GitHub Actions
- Terraform remediation generation

## Author

Vijay Thota

GitHub: https://github.com/VijayThota25
