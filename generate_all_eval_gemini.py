import os
import glob
import json
import time
import sys
import urllib.request
import urllib.error

OUTPUT_FILE = "evaluation_dataset.json"
MODEL_NAME = "gemini-2.5-flash"

def countdown_timer(seconds, message):
    """Displays a live countdown timer ticking down in the terminal."""
    for remaining in range(seconds, 0, -1):
        sys.stdout.write(f"\r  ⏳ {message} | Resuming in {remaining:03d}s...")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r" + " " * 90 + "\r")
    sys.stdout.flush()

def call_gemini_rest(prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            text_output = res_body["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_output)
    except urllib.error.HTTPError as e:
        error_message = e.read().decode("utf-8", errors="ignore")
        print(f"\n[HTTP Error Details]: {error_message}")
        return {"error_code": e.code, "reason": e.reason}
    except Exception as e:
        return {"error_code": 500, "reason": str(e)}

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is missing.")
        return

    all_files = sorted(glob.glob("corpus/**/*.md", recursive=True))
    if not all_files:
        print("Error: No markdown files found in 'corpus/'.")
        return

    existing_data = []
    processed_sources = set()
    
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                for item in existing_data:
                    if "source" in item:
                        processed_sources.add(item["source"])
            print(f"📁 Loaded Checkpoint: {len(processed_sources)} files already completed | {len(existing_data)} Q&A pairs generated so far.")
        except Exception as e:
            print(f"Note: Starting fresh (existing file unreadable: {e})")

    all_eval_data = list(existing_data)
    queue = [f for f in all_files if f not in processed_sources]
    
    if not queue:
        print(f"🎉 All corpus files have already been successfully processed! Total verified test items in '{OUTPUT_FILE}': {len(all_eval_data)}")
        return

    total_corpus_files = len(all_files)
    completed_count = len(processed_sources)
    total_questions = len(existing_data)
    remaining_to_process = len(queue)

    print(f"\n📊 Status Overview -> Model: {MODEL_NAME} | Total Files: {total_corpus_files} | Completed: {completed_count} | Remaining: {remaining_to_process} | Total Q&A Pairs: {total_questions}")
    print("=" * 80)
    
    session_processed = 0

    while queue:
        file_path = queue.pop(0)
        session_processed += 1
        completed_count += 1
        
        print(f"\n🚀 [{session_processed}/{remaining_to_process}] Processing File: {file_path}")
        print(f"   📈 Progress: {completed_count}/{total_corpus_files} files done ({completed_count/total_corpus_files*100:.1f}%) | Total Q&A: {total_questions}")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"  -> Error reading file: {e}")
            continue
            
        prompt = f"""
        You are an expert enterprise AI QA engineer. Based on the following document chunk, 
        generate 3 distinct, high-quality Q&A evaluation pairs (include factual metrics, numerical rules, or conditions).
        Return ONLY valid JSON with a key "pairs" containing a list of objects with keys "question" and "expected_context".
        
        Document Content:
        {content[:2500]}
        """
        
        result = call_gemini_rest(prompt, api_key)
        
        if isinstance(result, dict) and "error_code" in result:
            code = result["error_code"]
            print(f"  ❌ Error hit ({code}). Re-queueing file...")
            queue.append(file_path)
            completed_count -= 1
            countdown_timer(60, "Error Cool-down (1 min)")
        elif result and "pairs" in result:
            new_items = []
            for pair in result["pairs"]:
                new_items.append({
                    "id": f"test_case_{len(all_eval_data)+1:03d}",
                    "question": pair.get("question"),
                    "expected_context": pair.get("expected_context"),
                    "source": file_path
                })
            
            all_eval_data.extend(new_items)
            total_questions = len(all_eval_data)
            print(f"  ✅ Success! Added {len(new_items)} items. Total Q&A dataset size: {total_questions}")
            
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_eval_data, f, indent=2)
                
            countdown_timer(65, "API Rate-Limit Buffer")
        else:
            print(f"  ⚠️ Unexpected response format. Re-queueing file...")
            queue.append(file_path)
            completed_count -= 1
            countdown_timer(20, "Retry Buffer")

    print(f"\n✨ Full corpus processing complete! Total verified test items in '{OUTPUT_FILE}': {len(all_eval_data)}")

if __name__ == "__main__":
    main()
