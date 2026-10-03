"""อัปโหลด YodEdit ขึ้น Hugging Face Spaces (ฟรี)

ก่อนใช้: ล็อกอินครั้งเดียวด้วย  .venv\\Scripts\\hf auth login  (ใช้ token แบบ Write)
แล้วรัน:  .venv\\Scripts\\python deploy_hf.py  [ชื่อ Space, ค่าเริ่มต้น YodEdit]
"""
import sys
from pathlib import Path

from huggingface_hub import HfApi

FILES = [
    "README.md", "Dockerfile", ".dockerignore", "requirements.txt",
    "server.py", "static/*", "autocut/*.py",
]


def main():
    api = HfApi()
    user = api.whoami()["name"]
    repo_id = f"{user}/{sys.argv[1] if len(sys.argv) > 1 else 'YodEdit'}"
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(
        repo_id=repo_id, repo_type="space", folder_path=Path(__file__).parent,
        allow_patterns=FILES, commit_message="Deploy YodEdit",
    )
    print(f"https://huggingface.co/spaces/{repo_id}")


if __name__ == "__main__":
    main()
