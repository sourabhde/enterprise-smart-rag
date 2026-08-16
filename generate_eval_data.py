import os
import glob
import json
import urllib.request
import urllib.error

def call_openai_api(prompt, api_key):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode("utf-8"), 
        headers=headers, 
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            content = res_body["choices"][0]["message"]["content"]
            return json.loads(content)
    except urllib.error.HTTPError as e:
        print(f"API Error: {e.code} - {e.reason}")
        return None

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable is missing.")
        return

    files = glob.glob("corpus/**/*.md", recursive=True)
    if not files:
        print("Error: No markdown files found in 'corpus/'. Please run your corpus generator first.")
        return

    print(f"Found {len(files)} documents in corpus. Generating synthetic evaluation dataset via OpenAI...")
    
    all_eval_data = []
    
    # We sample or loop through core files to build a targeted, high-quality test suite
    for idx, file_path in enumerate(files[:15]):  # Process representative sample to optimize tokens/speed
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        prompt = f"""
        You are an expert enterprise AI QA engineer. Based on the following document chunk, 
        generate 3 distinct, high-quality Q&A evaluation pairs (include factual metrics, numerical rules, or conditions).
        Return a JSON object with a key "pairs" containing a list of objects with keys "question" and "expected_context".
        
        Document Content:
        {content[:2500]}
        """
        
        result = call_openai_api(prompt, api_key)
        if result and "pairs" in result:
            for pair in result["pairs"]:
                all_eval_data.append({
                    "id": f"test_case_{len(all_eval_data)+1:03d}",
                    "question": pair.get("question"),
                    "expected_context": pair.get("expected_context"),
                    "source": file_path
                })
        print(f"Processed [{idx+1}/{min(len(files), 15)}]: {file_path}")

    # Save to final golden dataset file
    with open("evaluation_dataset.json", "w", encoding="utf-8") as f:
        json.dump(all_eval_data, f, indent=2)
        
    print(f"\nSuccess! Generated {len(all_eval_data)} verified test items in 'evaluation_dataset.json'.")

if __name__ == "__main__":
    main()
