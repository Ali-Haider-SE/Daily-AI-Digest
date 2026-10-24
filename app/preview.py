"""Web preview generation and standalone preview server runner."""
import argparse
from pathlib import Path
from app.config import settings
from app.main import run as run_pipeline
from app.web.application import run_server

def generate_preview():
    print("[INFO] Generating latest email digest and web preview...")
    run_pipeline(dry_run=True)
    preview_file = Path("preview/digest.html")
    preview_file.parent.mkdir(parents=True, exist_ok=True)
    
    latest_file = settings.database_path.parent / "latest_digest.html"
    if latest_file.exists():
        preview_file.write_text(latest_file.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[SUCCESS] Email digest preview saved to: {preview_file.resolve()}")
    else:
        print("[WARNING] latest_digest.html was not generated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preview digest locally or serve interactive web portal.")
    parser.add_argument("--serve", action="store_true", help="Start local web server on port 8000")
    parser.add_argument("--port", type=int, default=8000, help="Web server port (default: 8000)")
    args = parser.parse_args()

    generate_preview()
    if args.serve:
        run_server(settings.web_host, args.port)
