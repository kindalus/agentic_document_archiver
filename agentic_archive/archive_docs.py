"""
Google Drive Document Archive Manager with Google AI

This script manages documents in Google Drive by using Google's Gemini AI to classify them
and organize them into appropriate folder structures based on their metadata.
"""

import argparse
import os
import traceback
from io import BytesIO

from agentic_document_classifier import classify_document
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from agentic_archive.pretty_print import pretty_print

# =============================================================================
# Version
# =============================================================================
__version__ = "0.1.0"

# =============================================================================
# Configuration from Environment Variables
# =============================================================================
SERVICE_ACCOUNT_KEY_PATH = os.environ.get("SERVICE_ACCOUNT_KEY_PATH")
ROOT_FOLDER_ID = os.environ.get("ROOT_FOLDER_ID")
IMPERSONATED_EMAIL = os.environ.get("IMPERSONATED_EMAIL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
COMPANY_FISCAL_ID = os.environ.get("COMPANY_FISCAL_ID")
COMPANY_NAME = os.environ.get("COMPANY_NAME")

# Validate required environment variables
required_env_vars = {
    "COMPANY_FISCAL_ID": COMPANY_FISCAL_ID,
    "COMPANY_NAME": COMPANY_NAME,
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "IMPERSONATED_EMAIL": IMPERSONATED_EMAIL,
    "ROOT_FOLDER_ID": ROOT_FOLDER_ID,
    "SERVICE_ACCOUNT_KEY_PATH": SERVICE_ACCOUNT_KEY_PATH,
}

missing_vars = [key for key, value in required_env_vars.items() if not value]
if missing_vars:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing_vars)}"
    )

# Global variables (initialized at runtime)
DRIVE_SERVICE = None
DROP_FOLDER_ID = None
UNCLASSIFIED_FOLDER_ID = None
LEFT_BEHIND_FOLDER_ID = None
ARCHIVE_ROOT_FOLDER_ID = None


# =============================================================================
# Constants
# =============================================================================

# COMMON API Configuration
DRIVE_API_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
]

# Console colors for output
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


# =============================================================================
# Utility Functions
# =============================================================================


def create_drive_service():
    """
    Creates and returns an authenticated Google Drive API service object.

    Returns:
        The authenticated Google Drive API service object
    """
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_KEY_PATH, scopes=DRIVE_API_SCOPES
    )
    delegated_creds = creds.with_subject(IMPERSONATED_EMAIL)
    return build("drive", "v3", credentials=delegated_creds)


def download_file(
    file_id: str, file_name: str, destination_folder: str = "/tmp"
) -> str | None:
    """
    Downloads a file from Google Drive by its ID.

    Args:
        file_id: The ID of the file to download
        file_name: The name of the file (used for saving)
        destination_folder: The folder to save the downloaded file

    Returns:
        The path to the downloaded file if successful, None otherwise
    """
    try:
        request = DRIVE_SERVICE.files().get_media(fileId=file_id)
        # Sanitize filename by replacing "/" with "_" to avoid invalid paths
        sanitized_file_name = file_name.replace("/", "_")
        file_path = f"{destination_folder}/{sanitized_file_name}"
        with open(file_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                _, done = downloader.next_chunk()
        return file_path
    except HttpError as error:
        print(f"{RED}An error occurred downloading file: {error}{RESET}")
        return None


def find_pdf_documents(service, parent_folder_id: str) -> tuple[list[str], list[str]]:
    """
    Searches for PDF documents in a specific folder.

    Args:
        service: The authenticated Google Drive API service object
        parent_folder_id: The ID of the folder to search in

    Returns:
        A tuple of (file_ids, file_names) for PDF documents found in the folder
    """
    try:
        files = []
        names = []
        page_token = None
        while True:
            response = (
                service.files()
                .list(
                    q=f"'{parent_folder_id}' in parents and mimeType = 'application/pdf'",
                    spaces="drive",
                    fields="nextPageToken, files(id, name)",
                    pageToken=page_token,
                )
                .execute()
            )

            for file in response.get("files", []):
                files.append(file.get("id"))
                names.append(file.get("name"))

            page_token = response.get("nextPageToken", None)
            if page_token is None:
                break

        return files, names

    except HttpError as error:
        print(f"{RED}An error occurred: {error}{RESET}")
        return [], []


def create_or_get_folder(service, folder_name: str, parent_id: str | None = None) -> str:
    """
    Creates a folder if it doesn't exist or retrieves its ID if it already exists.

    Args:
        service: The authenticated Google Drive API service object
        folder_name: The name of the folder
        parent_id: The ID of the parent folder

    Returns:
        The ID of the created or retrieved folder
    """
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    response = service.files().list(q=query, fields="files(id)").execute()
    folders = response.get("files", [])

    if folders:
        return folders[0]["id"]

    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        file_metadata["parents"] = [parent_id]

    folder = service.files().create(body=file_metadata, fields="id").execute()
    return folder["id"]


def create_folder_path(service, path_parts: list[str], root_folder_id: str) -> str:
    """
    Creates a folder structure based on a list of folder names.

    Args:
        service: The authenticated Google Drive API service object
        path_parts: A list of folder names representing the path
        root_folder_id: The ID of the root folder

    Returns:
        The ID of the deepest created folder
    """
    parent_folder_id = root_folder_id
    for folder_name in path_parts:
        parent_folder_id = create_or_get_folder(
            service, folder_name, parent_id=parent_folder_id
        )
    return parent_folder_id


def initialize_folder_structure(service) -> dict[str, str]:
    """
    Initialize the folder structure under ROOT_FOLDER_ID.
    Creates the following folders if they don't exist:
    - Drop: for incoming documents
    - Invalidos: for unclassified documents
    - Irrelevantes: for left behind documents
    - (Year folders are created as needed by the archiving process)

    Args:
        service: The authenticated Google Drive API service object

    Returns:
        A dictionary with folder IDs: {
            'drop': drop_folder_id,
            'unclassified': unclassified_folder_id,
            'left_behind': left_behind_folder_id,
            'archive_root': ROOT_FOLDER_ID
        }
    """
    print(f"{CYAN}Initializing folder structure under ROOT_FOLDER_ID...{RESET}")

    drop_folder_id = create_or_get_folder(service, "Drop", parent_id=ROOT_FOLDER_ID)
    print(f"{GREEN}✓ Drop folder ready: {drop_folder_id}{RESET}")

    unclassified_folder_id = create_or_get_folder(
        service, "Invalidos", parent_id=ROOT_FOLDER_ID
    )
    print(f"{GREEN}✓ Invalidos folder ready: {unclassified_folder_id}{RESET}")

    left_behind_folder_id = create_or_get_folder(
        service, "Irrelevantes", parent_id=ROOT_FOLDER_ID
    )
    print(f"{GREEN}✓ Irrelevantes folder ready: {left_behind_folder_id}{RESET}")

    return {
        "drop": drop_folder_id,
        "unclassified": unclassified_folder_id,
        "left_behind": left_behind_folder_id,
        "archive_root": ROOT_FOLDER_ID,  # pyright: ignore[reportReturnType]
    }


def upload_text_file_to_drive(service, content: str, file_name: str, parent_folder_id: str):
    """
    Upload a text file to Google Drive.

    Args:
        service: The authenticated Google Drive API service object
        content: The text content to upload
        file_name: The name for the file
        parent_folder_id: The ID of the parent folder

    Returns:
        The ID of the uploaded file
    """
    file_metadata = {
        "name": file_name,
        "parents": [parent_folder_id],
        "mimeType": "text/plain",
    }

    bytes_content = BytesIO(content.encode("utf-8"))
    media = MediaIoBaseUpload(bytes_content, mimetype="text/plain", resumable=True)

    _ = service.files().create(body=file_metadata, media_body=media, fields="id").execute()


# =============================================================================
# Archive Action Functions (Internal)
# =============================================================================


def _move_to_unclassified_internal(file_id: str, classification_result_text: str, reason: str):
    """
    Move a document to the unclassified folder when it cannot be properly archived.
    Also creates a text file with the classification results.

    Args:
        file_id: The ID of the file to move
        classification_result: The classification result string
        reason: The reason why the document is being moved to unclassified

    Returns:
        A confirmation message
    """

    # Get file info
    file = DRIVE_SERVICE.files().get(fileId=file_id, fields="id, name, parents").execute()
    file_name = file.get("name")

    parents = file.get("parents")
    previous_parents = ",".join(parents)

    DRIVE_SERVICE.files().update(
        fileId=file_id,
        body={"name": file.get("name")},
        addParents=UNCLASSIFIED_FOLDER_ID,
        removeParents=previous_parents,
        fields="id, parents",
    ).execute()

    # Create and upload classification results text file
    try:
        # Generate the text file name (replace .pdf with _results.txt)
        base_name = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
        results_file_name = f"{base_name}_results.txt"

        # Format classification results
        results_content = (
            classification_result_text + f"\n\nReason for unclassified: {reason}\n"
        )

        # Upload the text file to the same folder
        upload_text_file_to_drive(
            DRIVE_SERVICE, results_content, results_file_name, UNCLASSIFIED_FOLDER_ID
        )

    except Exception as e:
        print(f"{YELLOW}Warning: Could not create results file: {e}{RESET}")


# =============================================================================
# AI-Callable Tool Functions (for automatic function calling)
# =============================================================================


def archive_move_to_folder(file_id: str, path: str, new_name: str = None) -> None:
    """Move the current document to a specific folder path for archiving.

    Use this for standard document archiving based on year/month structure.
    The path should be relative to the archive root folder.

    Args:
        file_id: The Google Drive file ID of the document to move
        path: Folder path relative to archive root, e.g. "2024/2024-01/Impostos"
        new_name: Optional new filename with .pdf extension, e.g. "2024-01-15 - FACTURA 123.pdf"
    """

    # Parse the path and create folder structure under ARCHIVE_ROOT_FOLDER_ID
    path_parts = path.split("/")
    parent_folder_id = create_folder_path(DRIVE_SERVICE, path_parts, ARCHIVE_ROOT_FOLDER_ID)

    # Get current file info
    file = DRIVE_SERVICE.files().get(fileId=file_id, fields="name, parents").execute()
    previous_parents = ",".join(file.get("parents"))

    # Prepare the new name
    final_name = new_name if new_name else file.get("name")

    # Move the file
    DRIVE_SERVICE.files().update(
        fileId=file_id,
        body={"name": final_name},
        addParents=parent_folder_id,
        removeParents=previous_parents,
        fields="id, parents",
    ).execute()


def archive_copy_to_folder(file_id: str, path: str, new_name: str = None) -> None:
    """Copy the current document to a specific folder path.

    Use this when the document needs to be in multiple locations.
    The original file remains in its current location.

    Args:
        file_id: The Google Drive file ID of the document to copy
        path: Folder path relative to archive root, e.g. "2024/2024-01/Frete"
        new_name: Optional new filename with .pdf extension
    """

    # Parse the path and create folder structure under ARCHIVE_ROOT_FOLDER_ID
    path_parts = path.split("/")
    parent_folder_id = create_folder_path(DRIVE_SERVICE, path_parts, ARCHIVE_ROOT_FOLDER_ID)

    # Get current file info
    file = DRIVE_SERVICE.files().get(fileId=file_id, fields="name").execute()
    final_name = new_name if new_name else file.get("name")

    # Copy the file
    DRIVE_SERVICE.files().copy(
        fileId=file_id, body={"name": final_name, "parents": [parent_folder_id]}
    ).execute()


def archive_move_to_left_behind(file_id: str, path: str, new_name: str | None = None) -> None:
    """Move the current document to the left behind folder for manual review.

    Use this for documents that need additional review or processing.
    The document will be organized by year/month in the Irrelevantes folder.

    Args:
        file_id: The Google Drive file ID of the document to move
        path: Folder path relative to left behind folder, e.g. "2024/2024-01"
        new_name: Optional new filename with .pdf extension
    """

    # Parse the path and create folder structure under LEFT_BEHIND_FOLDER_ID
    path_parts = path.split("/")
    parent_folder_id = create_folder_path(DRIVE_SERVICE, path_parts, LEFT_BEHIND_FOLDER_ID)

    # Get current file info
    file = DRIVE_SERVICE.files().get(fileId=file_id, fields="name, parents").execute()
    previous_parents = ",".join(file.get("parents"))

    # Prepare the new name
    final_name = new_name if new_name else file.get("name")

    # Move to left behind folder
    DRIVE_SERVICE.files().update(
        fileId=file_id,
        body={"name": final_name},
        addParents=parent_folder_id,
        removeParents=previous_parents,
        fields="id, parents",
    ).execute()


def archive_move_to_unclassified(file_id: str, reason: str) -> None:
    """Move the current document to the unclassified folder.

    Use this when:
    - Document does not belong to our company
    - Document type is not supported
    - Missing required metadata for proper archiving
    - Classification was uncertain or ambiguous

    Args:
        file_id: The Google Drive file ID of the document to move
        reason: Clear explanation of why the document cannot be archived properly, include the entire classification
    """
    # Classification details are in the AI prompt context, create a note with the reason
    classification_note = f"Document moved to unclassified by AI agent.\n\nReason: {reason}"
    _move_to_unclassified_internal(file_id, classification_note, reason)


# =============================================================================
# Google AI Archive Agent
# =============================================================================


def get_archive_system_prompt() -> str:
    """System prompt that defines the agent's role and decision-making rules."""
    return f"""You are a document archiving specialist for a multi-company organization.

Your task is to analyze classified documents and decide how to archive them based on the following rules.

**OUR COMPANY IDENTIFIERS**:
- Company Fiscal ID (NIF): {COMPANY_FISCAL_ID}
- Company Name: {COMPANY_NAME}

**DOCUMENT GROUPS AND ARCHIVING RULES**:

     FACTURA_GLOBAL = "FACTURA_GLOBAL"
     FACTURA_GENERICA = "FACTURA_GENERICA"
     NOTA_DEBITO = "NOTA_DEBITO"
     NOTA_CREDITO = "NOTA_CREDITO"
     RECIBO = "RECIBO"
     OUTRO_DOCUMENTO = "OUTRO_DOCUMENTO"

1. **DOCUMENTOS_COMERCIAIS (Commercial Documents)**:
   - If document type is FACTURA_PRO_FORMA: move_to_unclassified
   - Check if nif_emitente == {COMPANY_FISCAL_ID}: We are the vendor
     - RECIBO: Archive to: {{{{year}}}}/{{{{year-month}}}}/[Facturas - Recibos - Clientes]
     - FACTURA_RECIBO, FACTURA, FACTURA_GLOBAL, FACTURA_GENERICA, NOTA_DE_CREDITO, NOTA_DEBITO:  Archive to: {{{{year}}}}/{{{{year-month}}}}/[Facturas - Clientes]
     - Filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf
   - Check if nif_cliente == {COMPANY_FISCAL_ID}: We are the client
     - RECIBOS: Archive to: {{{{year}}}}/{{{{year-month}}}}/Recibos - Fornecedores]
     - FACTURA_RECIBO, FACTURA, FACTURA_GLOBAL, FACTURA_GENERICA, NOTA_DE_CREDITO, NOTA_DEBITO: Archive to: {{{{year}}}}/{{{{year-month}}}}/[Facturas - Fornecedores]
     - Filename: {{{{date}}}} - {{{{vendor_name}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf
   - If neither matches: move_to_unclassified

2. **DOCUMENTOS_ADUANEIROS (Customs Documents)**:
   - NOTA_LIQUIDACAO:
     - copy_to_folder to {{{{year}}}}/{{{{year-month}}}}/Impostos
       - Copy filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf
     - move_to_left_behind
       - Left behind filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf
   - RECIBO:
     - copy_to_folder to {{{{year}}}}/{{{{year-month}}}}/Impostos - Liquidacoes
       - Copy filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf
     - move_to_left_behind
       - Left behind filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf
   - Other types: move_to_left_behind
     - Filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf

3. **DOCUMENTOS_FISCAIS (Tax Documents)**:
   - Check if nif_contribuinte == {COMPANY_FISCAL_ID} or nome_contribuinte matches "{COMPANY_NAME}"
   - If yes:
     - Archive to: {{{{year}}}}/{{{{year-month}}}}/Impostos
     - Filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf
   - Otherwise: move_to_unclassified

4. **DOCUMENTOS_BANCARIOS (Banking Documents)**:
   - Archive to: {{{{year}}}}/{{{{year-month}}}}/Bancos
   - Filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf

5. **DOCUMENTOS_FRETE (Freight Documents)**:
   - Filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf
   - Then move_to_left_behind (do not use move_to_unclassified)

6. **DOCUMENTOS_RH (Human Resources Documents)**:
   - FOLHA_REMUNERACAO:
     - Filename: Salarios {{{{mes_referencia}}}}.pdf
     - Archive to: {{{{year}}}}/{{{{year-month}}}}/Salarios
   - Other types: move_to_left_behind
     - Filename: {{{{date}}}} - {{{{document_type}}}} {{{{document_number}}}}.pdf

7. **OUTROS_DOCUMENTOS (Other Documents)**:
   - Always: move_to_unclassified

**DECISION PROCESS**:
1. Analyze the classification result including document group and metadata
2. Compare document identifiers (NIF, company names) against our company identifiers
3. Determine which archiving rule applies based on document type and company match
4. Decide on appropriate filenames based on the document type and metadata
5. Call the appropriate archiving tool function(s) to execute the actions

**IMPORTANT**:
- Use archive_copy_to_folder when document needs to be in multiple locations (call it first, then call another function)
- Use archive_move_to_folder for standard archiving
- Use archive_move_to_unclassified when document cannot be classified or doesn't match our company
- Use archive_move_to_left_behind for documents needing manual review
- You decide the final filename - make it descriptive and follow the patterns shown in the rules
- Handle special characters in filenames appropriately for filesystem compatibility
- Always compare NIFs and company names against our company identifiers to ensure documents belong to us
- In Angola company names often have the company activity scope and legal status, for example: Zafir - Tecnologia, Lda
  - When it is present in company's name, just remove it. example: Ubiquus - Representacoes, Lda ==> Ubiquus

**AVAILABLE TOOLS**:
- archive_move_to_folder(file_id, path, new_name): Move document to archive folder
- archive_copy_to_folder(file_id, path, new_name): Copy document to archive folder (original stays)
- archive_move_to_left_behind(file_id, path, new_name): Move to left behind folder for review
- archive_move_to_unclassified(file_id, reason): Move to unclassified folder with reason


**IMPORTANT**: The file_id parameter will be provided in the user prompt. Use it when calling the tools.

When moving files to uclassified folder, include the entire classification result in the reason explanation
Format the classification result to a key-value format with a maximum of 100 chars per line, wrap lines if needed
"""


def archive_with_ai(file_id: str, classification_result) -> None:
    """
    Uses Google AI to make archiving decisions and execute them.

    Args:
        file_id: The ID of the file to archive
        classification_result: The classification result from classify_document
    """
    # Initialize Google AI client
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Handle error cases upfront
    if classification_result is None:
        _move_to_unclassified_internal(
            file_id,
            pretty_print(classification_result),
            "Failed to classify document",
        )
        return

    # Check if classification returned an error
    if hasattr(classification_result, "erro"):
        _move_to_unclassified_internal(
            file_id,
            pretty_print(classification_result),
            f"Classification error: {classification_result.erro}",
        )
        return

    # Create a detailed prompt for the AI
    prompt = f"""Analyze and archive this document using the available tools:

**Classification Result**:
- Document Group: {classification_result.grupo_documento}
- Document Type: {getattr(classification_result, "tipo_documento", "N/A")}
- Issue Date: {getattr(classification_result, "data_emissao", "N/A")}
- Document Number: {getattr(classification_result, "numero_documento", "N/A")}

Based on the archiving rules in your system prompt, call the appropriate archiving tool function(s) to process this document.
You may need to call multiple functions (e.g., copy_to_folder then move_to_left_behind).

**FILE IDENTIFIER**:
The `file_id` to use with tools is `{file_id}`

**COMPLETE DOCUMENT CLASSIFICATION RESULTS**:
{classification_result.model_dump_json(indent=4)}
"""

    try:
        # Call Google AI with automatic function calling
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=get_archive_system_prompt(),
                tools=[
                    archive_move_to_folder,
                    archive_copy_to_folder,
                    archive_move_to_left_behind,
                    archive_move_to_unclassified,
                ],
                temperature=0.2,
            ),
        )

        # The SDK automatically executes the function calls
        print(f"\n{GREEN}AI archiving completed{RESET}")
        if response.text:
            print(f"{GREEN}Summary: {response.text}{RESET}")

    except Exception as e:
        print(f"{RED}AI error when trying to archive document: {e}{RESET}")
        traceback.print_exc()
        # On AI error, move to unclassified
        try:
            _move_to_unclassified_internal(
                file_id,
                pretty_print(classification_result),
                f"AI error: {str(e)}",
            )
        except Exception as e2:
            print(f"{RED}Failed to move to unclassified: {e2}{RESET}")


# =============================================================================
# Main Execution
# =============================================================================


def process_document(file_id: str, file_name: str, destination_folder: str = "/tmp"):
    """
    Processes a document by downloading and classifying it.

    Args:
        file_id: The ID of the document to process
        file_name: The name of the file
        destination_folder: The folder to save downloaded files

    Returns:
        The classification result or None if classification failed
    """
    file_path = None
    try:
        file_path = download_file(file_id, file_name, destination_folder)

        if file_path:
            result = classify_document(file_path)

            # Delete the temporary file after classification
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(
                    f"{YELLOW}Warning: Could not delete temporary file {file_path}: {e}{RESET}"
                )

            return result
    except Exception as error:
        print(f"{RED}An error occurred during classification: {error}{RESET}")
        # Attempt cleanup on error
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None


def main():
    """
    Main function that executes the document classification and archiving workflow.
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Google Drive Document Archive Manager with Google AI",
        prog="agentic-archive",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args()

    global \
        DRIVE_SERVICE, \
        DROP_FOLDER_ID, \
        UNCLASSIFIED_FOLDER_ID, \
        LEFT_BEHIND_FOLDER_ID, \
        ARCHIVE_ROOT_FOLDER_ID

    # Create the Drive service
    DRIVE_SERVICE = create_drive_service()

    # Initialize folder structure
    folder_ids = initialize_folder_structure(DRIVE_SERVICE)
    DROP_FOLDER_ID = folder_ids["drop"]
    UNCLASSIFIED_FOLDER_ID = folder_ids["unclassified"]
    LEFT_BEHIND_FOLDER_ID = folder_ids["left_behind"]
    ARCHIVE_ROOT_FOLDER_ID = folder_ids["archive_root"]

    print(f"\n{CYAN}Folder structure initialized{RESET}")

    # Scan for PDF documents
    file_ids, file_names = find_pdf_documents(DRIVE_SERVICE, DROP_FOLDER_ID)
    print(f"{GREEN}Found {len(file_ids)} PDF documents in the drop folder.{RESET}")

    # Process each document
    for file_id, file_name in zip(file_ids, file_names, strict=False):
        print(f"\n{CYAN}Processing file: {file_name}{RESET}")
        print(f"{CYAN}{'=' * 95}{RESET}")

        # Download and classify
        classification_result = process_document(file_id, file_name)

        if classification_result is None:
            print(f"{RED}Failed to classify document: {file_id}{RESET}")
            continue

        print(f"\nName:\t{classification_result.localizacao_ficheiro}")
        print(f"Numero:\t{getattr(classification_result, 'numero_documento', 'N/A')}")
        print(f"Grupo:\t{getattr(classification_result, 'grupo_documento', 'N/A')}")
        print(f"Tipo:\t{getattr(classification_result, 'tipo_documento', 'N/A')}")
        print(f"Notas:\t{getattr(classification_result, 'notas_triagem', 'N/A')}\n")

        # Archive using Google AI
        archive_with_ai(file_id, classification_result)


if __name__ == "__main__":
    main()
