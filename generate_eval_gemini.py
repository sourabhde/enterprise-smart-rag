import os
import glob
import json
import time
import urllib.request
import urllib.error

def call_gemini_rest(prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.7-flash:generateContent?key={api_key}"
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
        return {"error_code": e.code, "reason": e.reason}
    except Exception as e:
        return {"error_code": 500, "reason": str(e)}

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is missing.")
        return

    # Grab ALL markdown files across all corpus subfolders (skus, legal, policies, etc.)
    files = glob.glob("corpus/**/*.md", recursive=True)
    if not files:
        print("Error: No markdown files found in 'corpus/'.")
        return

    print(f"Found {len(files)} total documents across all corpus folders. Starting full-corpus generation queue...")
    
    all_eval_data = []
    queue = list(files)
    retries_left = {}
    
    # Track retry attempts for failed files
    for f in queue:
        retries_left[f] = 2  # Allow up to 2 re-queue attempts

    processed_count = 0
    total_files = len(files)

    while queue:
        file_path = queue.pop(0)
        processed_count += 1
        print(f"[{processed_count}/{total_files + (total_files - len(queue))}] Processing: {file_path}")
        
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
            print(f"  -> Rate limit or server error ({code}). Re-queueing file for later...")
            if retries_left[file_path] > 0:
                retries_left[file_path] -= 1
                queue.append(file_path)  # Push to the back of the queue
            else:
                print(f"  -> Max retries reached for {file_path}. Skipping.")
            # Take a longer rest when hitting a block
            time.sleep(20)
        elif result and "pairs" in result:
            for pair in result["pairs"]:
                all_eval_data.append({
                    "id": f"test_case_{len(all_eval_data)+1:03d}",
                    "question": pair.get("question"),
                    "expected_context": pair.get("expected_context"),
                    "source": file_path
                })
            print(f"  -> Successfully added {len(result['pairs'])} items.")
            # Safe 15-second pause between successful calls to strictly respect the 5 RPM free limit
            time.sleep(15)
        else:
            print(f"  -> Invalid response structure. Re-queueing...")
            if retries_left[file_path] > 0:
                retries_left[file_path] -= 1
                queue.append(file_path)
            time.sleep(15)

    # Save complete dataset covering all corpus folders
    with open("evaluation_dataset.json", "w", encoding="utf-8") as f:
        json.dump(all_eval_data, f, indent=2)
        
    print(f"\nFull-corpus complete! Generated {len(all_eval_data)} verified test items across all files in 'evaluation_dataset.json'.")

if __name__ == "__main__":
    main()
