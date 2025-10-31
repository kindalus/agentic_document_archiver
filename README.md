# Agentic Archive

Google Drive Document Archive Manager with Pydantic AI - An intelligent system for automatically classifying and organizing documents in Google Drive using AI-powered decision making.

## Features

- **AI-Powered Classification**: Uses Pydantic AI with Google's Gemini model to intelligently classify and route documents
- **Google Drive Integration**: Seamlessly works with Google Drive API for document management
- **Flexible Organization**: Automatically organizes documents into year/month-based folder structures
- **Smart Decision Making**: AI agent makes contextual decisions based on document metadata
- **Multiple Document Types**: Supports commercial, customs, tax, banking, freight, and HR documents

## Installation

### Prerequisites

- Python 3.9 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Install uv (if not already installed)

```bash
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install the Package

#### Option 1: Install from source (for development)

```bash
# Clone the repository
git clone git@github.com:kindalus/agentic_document_archiver.git
cd agentic_document_archiver

# Create a virtual environment and install the package
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package in editable mode with dependencies
# This will automatically install agentic-document-classifier from GitHub
uv pip install -e .

# Or install with development dependencies
uv pip install -e ".[dev]"
```

**Note**: The `agentic-document-classifier` dependency is automatically installed from GitHub (https://github.com/kindalus/agentic_document_classifier.git) as part of the installation process.

#### Option 2: Install directly with uv

```bash
# Install from local directory
uv pip install /path/to/agentic_document_archiver

# Or install directly from GitHub
uv pip install git+https://github.com/kindalus/agentic_document_archiver.git

# Or if published to PyPI (future)
uv pip install agentic-archive
```

## Configuration

1. **Copy the example environment file:**

```bash
cp .env.example .env
```

2. **Edit `.env` with your configuration:**

```bash
# Google Drive Configuration
SERVICE_ACCOUNT_KEY_PATH=/path/to/your/service-account-key.json
ROOT_FOLDER_ID=your_root_folder_id_here
IMPERSONATED_EMAIL=user@example.com

# Google API Configuration
GOOGLE_API_KEY=your_google_api_key_here

# Company Information
COMPANY_FISCAL_ID=your_company_nif_here
COMPANY_NAME=Your Company Name
```

3. **Load environment variables:**

```bash
# Option 1: Use a tool like direnv
# Option 2: Source manually
source .env

# Option 3: Export each variable
export SERVICE_ACCOUNT_KEY_PATH=/path/to/key.json
# ... etc
```

## Usage

### Running with uv

Once installed, you can run the archive manager in several ways:

#### Option 1: Using the installed command

```bash
# Make sure your virtual environment is activated
source .venv/bin/activate

# Run the command
agentic-archive
```

#### Option 2: Using uv run (recommended)

```bash
# Run directly with uv (automatically handles dependencies)
uv run agentic-archive
```

#### Option 3: As a Python module

```bash
# Run as a module
uv run python -m agentic_archive.archive_docs
```

#### Option 4: Using the package programmatically

```python
from agentic_archive import create_drive_service, main

# Use the main function
main()

# Or use individual functions
service = create_drive_service()
# ... your custom logic
```

### Development Workflow with uv

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install with dev dependencies
uv pip install -e ".[dev]"

# Run the application
uv run agentic-archive

# Run tests (when available)
uv run pytest

# Format code
uv run black .

# Lint code
uv run ruff check .

# Type checking
uv run mypy agentic_archive
```

### Sync dependencies with uv

```bash
# Sync dependencies from pyproject.toml
uv pip sync

# Update all dependencies
uv pip compile pyproject.toml -o requirements.txt
uv pip sync requirements.txt
```

## Project Structure

```
agentic_document_archiver/
├── agentic_archive/
│   ├── __init__.py           # Package initialization
│   └── archive_docs.py       # Main application logic
├── pyproject.toml            # Project configuration and dependencies
├── README.md                 # This file
├── .env.example              # Example environment configuration
├── .gitignore                # Git ignore rules
└── uv.lock                   # Dependency lock file
```

## How It Works

1. **Folder Initialization**: Creates a structured folder hierarchy in Google Drive
   - `Drop/` - Incoming documents
   - `Invalidos/` - Unclassified documents
   - `Irrelevantes/` - Documents for review
   - Year-based folders for organized archives

2. **Document Processing**:
   - Scans the Drop folder for PDF documents
   - Downloads and classifies each document using AI
   - Extracts metadata (dates, company info, document types)

3. **AI-Powered Archiving**:
   - AI agent analyzes classification results
   - Makes decisions based on document type and metadata
   - Automatically files documents in appropriate folders
   - Creates descriptive filenames

4. **Document Types Supported**:
   - Commercial documents (invoices, receipts)
   - Customs documents
   - Tax documents
   - Banking documents
   - Freight documents
   - HR documents (payroll, etc.)

## Environment Variables

| Variable                   | Description                                  | Required |
| -------------------------- | -------------------------------------------- | -------- |
| `SERVICE_ACCOUNT_KEY_PATH` | Path to Google service account JSON key      | Yes      |
| `ROOT_FOLDER_ID`           | Google Drive root folder ID for organization | Yes      |
| `IMPERSONATED_EMAIL`       | Email for domain-wide delegation             | Yes      |
| `GOOGLE_API_KEY`           | Google API key for Gemini AI                 | Yes      |
| `COMPANY_FISCAL_ID`        | Your company's tax ID (NIF)                  | Yes      |
| `COMPANY_NAME`             | Your company name                            | Yes      |

## Dependencies

- `google-auth` - Google authentication
- `google-api-python-client` - Google Drive API client
- `pydantic-ai` - AI agent framework
- `pydantic` - Data validation

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues and questions, please open an issue on the [GitHub repository](https://github.com/kindalus/agentic_document_archiver/issues).

## Repository

- **GitHub**: https://github.com/kindalus/agentic_document_archiver
- **Clone**: `git clone git@github.com:kindalus/agentic_document_archiver.git`
