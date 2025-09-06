import os
import argparse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_file(file_path: str, folder_id: str):
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json",
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    drive = build("drive", "v3", credentials=creds)

    file_metadata = {"name": os.path.basename(file_path), "parents": [folder_id]}
    media = MediaFileUpload(file_path, resumable=True)
    file = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    print("Uploaded file ID:", file.get("id"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",   required=True, help="Path to file to upload")
    parser.add_argument("--folder", required=True, help="Drive folder ID")
    args = parser.parse_args()
    upload_file(args.file, args.folder)
