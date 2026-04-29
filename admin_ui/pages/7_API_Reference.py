import streamlit as st

from admin_ui._url_fix import fix_url

st.set_page_config(page_title="API Reference", layout="wide")
fix_url()
st.title("API Reference")

st.markdown("""
All API endpoints require an **`X-API-Key`** header for authentication.
The client must have an active plan and the relevant template must be granted.

Base URL: `https://your-server.example.com`
""")

st.divider()

# -- OCR endpoint --
st.subheader("POST /api/v1/ocr")
st.markdown("""
Submit a document for OCR processing. Returns a job ID immediately (async/queued).

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | One of `file` / `files` | Single-page request — Image (JPEG/PNG/TIFF) |
| `files` | file (repeated) | One of `file` / `files` | Multi-page request — repeat the field once per page (`-F files=@p0.png -F files=@p1.png ...`). Total pages must be ≤ plan's `max_pages_per_txn`. |
| `doc_type` | string | No | Template `doc_type_code` for structured extraction |
| `page_indexes` | string (JSON) | No | JSON array mapping each uploaded file to its logical page index, e.g. `"[1,0,2]"`. Length must equal file count; values must be unique non-negative ints. Defaults to upload order (`[0,1,...]`). |
| `Idempotency-Key` | header | No | Prevent duplicate submissions |

> **Page tagging:** by default each `files` upload is tagged with its
> upload-order index — first becomes `page_index=0`, second `page_index=1`.
> Send `page_indexes` to override when uploads are not in document order.
""")

with st.expander("OCR: single-page request"):
    st.markdown("**Request:**")
    st.code("""
curl -X POST https://your-server.example.com/api/v1/ocr \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -F "file=@document.jpeg" \\
  -F "doc_type=sijil_ssm"
""", language="bash")

with st.expander("OCR: multi-page request"):
    st.markdown("**Request (3 pages in one transaction):**")
    st.code("""
curl -X POST https://your-server.example.com/api/v1/ocr \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -F "files=@page0.png" \\
  -F "files=@page1.png" \\
  -F "files=@page2.png" \\
  -F "doc_type=sijil_ssm"
""", language="bash")
    st.caption("Counts as **1** transaction against `max_transactions`. "
               "Counts as **3 pages** against `max_pages_per_txn` "
               "(must be ≤ plan limit, otherwise 400).")

with st.expander("OCR: multi-page with explicit page indexes"):
    st.markdown("Use `page_indexes` when uploads are not in document order:")
    st.code("""
curl -X POST https://your-server.example.com/api/v1/ocr \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -F "files=@scan_b.png"  \\
  -F "files=@scan_a.png"  \\
  -F "files=@scan_c.png"  \\
  -F "page_indexes=[1,0,2]" \\
  -F "doc_type=sijil_ssm"
""", language="bash")
    st.markdown("""
    With this body:
    - `scan_b.png` is tagged as `page_index=1`
    - `scan_a.png` is tagged as `page_index=0`
    - `scan_c.png` is tagged as `page_index=2`

    A field with template `page_index=0` reads `scan_a.png`'s OCR lines.

    **Rules:**
    - Length must equal the number of `files` uploaded
    - Values must be unique non-negative integers
    - Sparse allowed (e.g. `[0,2,5]`); fields targeting absent pages return null
    - Omit the field entirely to use upload order (`[0,1,...]`)
    """)

    st.markdown("**Response (202 Accepted):**")
    st.json({"job_id": "4ec0eecc-214e-4bc0-86b0-e7b5c4447c88", "status": "queued"})

    st.markdown("**Without `doc_type`:** Returns raw OCR lines (no template extraction).")
    st.markdown("**With `doc_type`:** Returns OCR lines + extracted fields based on template.")

st.divider()

# -- Verify endpoint --
st.subheader("POST /api/v1/verify")
st.markdown("""
Submit a document with expected field values for verification. Queued like OCR.
The engine extracts fields using the template, then compares against your expected values.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | One of `file` / `files` | Single-page request — Image (JPEG/PNG/TIFF) |
| `files` | file (repeated) | One of `file` / `files` | Multi-page request — repeat the field once per page. |
| `doc_type` | string | Yes | Template `doc_type_code` |
| `expected_fields` | string (JSON) | Yes | JSON object of `field_name: expected_value` pairs |
| `Idempotency-Key` | header | No | Prevent duplicate submissions |
""")

with st.expander("Verify: example request & response"):
    st.markdown("**Request:**")
    st.code("""
curl -X POST https://your-server.example.com/api/v1/verify \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -F "file=@sijil_ssm.jpeg" \\
  -F "doc_type=sijil_ssm" \\
  -F 'expected_fields={"nama_perniagaan":"DFG TELECOMMUNICATION","no_pendaftaran":"MA0127232-D"}'
""", language="bash")

    st.markdown("**Response (202 Accepted):**")
    st.json({"job_id": "a1b2c3d4-...", "status": "queued"})

    st.markdown("**Completed result** (via `/api/v1/jobs/{job_id}`):")
    st.json({
        "verified": True,
        "fields": {
            "nama_perniagaan": {
                "expected": "DFG TELECOMMUNICATION",
                "extracted": "DFG TELECOMMUNICATION",
                "match": True,
            },
            "no_pendaftaran": {
                "expected": "MA0127232-D",
                "extracted": "MA0127232-D",
                "match": True,
            },
        },
        "all_extracted": {
            "nama_perniagaan": "DFG TELECOMMUNICATION",
            "no_pendaftaran": "MA0127232-D",
        },
        "template_id": 52,
        "template_version": 6,
        "extraction_errors": None,
    })

    st.markdown("""
    **Comparison logic:**
    - Case-insensitive
    - Whitespace, colons, hyphens, dots, commas collapsed before comparison
    - `verified: true` only when **all** expected fields match
    """)

st.divider()

# -- Jobs endpoint --
st.subheader("GET /api/v1/jobs/{job_id}")
st.markdown("""
Poll for the result of a submitted OCR or Verify job.

| Status | Meaning |
|--------|---------|
| `queued` | Job is waiting in the queue |
| `running` | OCR is in progress |
| `done` | Completed -- `result` field contains output |
| `failed` | Error occurred -- `error` field contains message |
""")

with st.expander("Jobs: example response"):
    st.markdown("**Polling (still running):**")
    st.json({
        "job_id": "4ec0eecc-...",
        "status": "running",
        "pages_submitted": 1,
        "queued_at": "2026-04-18T12:36:16.735756+00:00",
    })

    st.markdown("**Completed (OCR with template):**")
    st.json({
        "job_id": "4ec0eecc-...",
        "status": "done",
        "pages_submitted": 1,
        "queued_at": "2026-04-18T12:36:16+00:00",
        "completed_at": "2026-04-18T12:36:51+00:00",
        "result": {
            "lines": [{"text": "...", "confidence": 0.99, "bbox": [0, 0, 100, 20]}],
            "fields": {"nama_perniagaan": "DFG TELECOMMUNICATION"},
            "template_id": 52,
            "template_version": 6,
        },
    })

    st.markdown("**Recommended polling interval:** every 3-5 seconds. "
                "First request may take 30-60s if OCR engine is cold-starting.")

st.divider()

# -- Workflow --
st.subheader("Typical integration workflow")
st.markdown("""
```
1. Admin creates template + uploads sample image
2. Admin annotates fields (zone/anchor/regex/between) on Annotate page
3. Admin grants template to client (Client Templates page)
4. Client app submits document:
     POST /api/v1/ocr   (extract fields)
     POST /api/v1/verify (extract + compare expected values)
5. Client app polls:
     GET /api/v1/jobs/{job_id}
     repeat every 3-5s until status = "done" or "failed"
6. Client app reads result from response
```
""")

st.subheader("Error codes")
st.markdown("""
| HTTP Code | Error | Meaning |
|-----------|-------|---------|
| 401 | `auth_error` | Missing or invalid `X-API-Key` |
| 400 | `bad_request` | Invalid input (empty file, bad JSON, no plan) |
| 403 | `forbidden` | Template not granted to this client |
| 404 | `not_found` | Template or job not found |
| 409 | `idempotency_conflict` | Same idempotency key, different file |
| 429 | `quota_exceeded` | Plan transaction limit reached |
""")

st.divider()

# ── Code examples ─────────────────────────────────────────────────────────────
st.header("Integration code examples")
st.markdown("""
All examples follow the same pattern:
1. **Submit** document to `/api/v1/verify` (or `/api/v1/ocr`)
2. **Receive** `job_id` immediately
3. **Poll** `/api/v1/jobs/{job_id}` every 3-5 seconds until `done` or `failed`
4. **Read** result from response

Replace `YOUR_API_KEY` and `YOUR_DOC_TYPE` with actual values.
""")

lang = st.selectbox("Select language", [
    "Python", "PHP", "C# (.NET)", "JavaScript (Node.js)",
    "Java", "Go", "cURL (Bash)",
])

if lang == "Python":
    st.code('''
import requests
import time
import json

API_URL = "https://your-server.example.com"
API_KEY = "YOUR_API_KEY"

def verify_document(file_path, doc_type, expected_fields):
    """Submit document for verification and poll for result."""

    # 1. Submit
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{API_URL}/api/v1/verify",
            headers={"X-API-Key": API_KEY},
            files={"file": f},
            data={
                "doc_type": doc_type,
                "expected_fields": json.dumps(expected_fields),
            },
        )
    resp.raise_for_status()
    job_id = resp.json()["job_id"]
    print(f"Submitted: job_id={job_id}")

    # 2. Poll
    while True:
        r = requests.get(
            f"{API_URL}/api/v1/jobs/{job_id}",
            headers={"X-API-Key": API_KEY},
        )
        r.raise_for_status()
        data = r.json()

        if data["status"] == "done":
            return data["result"]
        elif data["status"] == "failed":
            raise Exception(f"Job failed: {data.get('error')}")

        time.sleep(3)


# Usage
result = verify_document(
    "sijil_ssm.jpeg",
    "sijil_ssm",
    {
        "nama_perniagaan": "DFG TELECOMMUNICATION",
        "no_pendaftaran": "MA0127232-D",
    },
)
print(f"Verified: {result['verified']}")
for name, info in result["fields"].items():
    status = "MATCH" if info["match"] else "MISMATCH"
    print(f"  {name}: {status} (expected={info['expected']}, got={info['extracted']})")
''', language="python")

elif lang == "PHP":
    st.code('''
<?php
$apiUrl = "https://your-server.example.com";
$apiKey = "YOUR_API_KEY";

function verifyDocument($filePath, $docType, $expectedFields) {
    global $apiUrl, $apiKey;

    // 1. Submit
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL            => "$apiUrl/api/v1/verify",
        CURLOPT_POST           => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER     => ["X-API-Key: $apiKey"],
        CURLOPT_POSTFIELDS     => [
            "file"             => new CURLFile($filePath, "image/jpeg"),
            "doc_type"         => $docType,
            "expected_fields"  => json_encode($expectedFields),
        ],
    ]);
    $resp = json_decode(curl_exec($ch), true);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($httpCode !== 202) {
        throw new Exception("Submit failed: " . json_encode($resp));
    }
    $jobId = $resp["job_id"];
    echo "Submitted: job_id=$jobId\\n";

    // 2. Poll
    while (true) {
        $ch = curl_init();
        curl_setopt_array($ch, [
            CURLOPT_URL            => "$apiUrl/api/v1/jobs/$jobId",
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HTTPHEADER     => ["X-API-Key: $apiKey"],
        ]);
        $data = json_decode(curl_exec($ch), true);
        curl_close($ch);

        if ($data["status"] === "done") {
            return $data["result"];
        } elseif ($data["status"] === "failed") {
            throw new Exception("Job failed: " . ($data["error"] ?? "unknown"));
        }

        sleep(3);
    }
}

// Usage
$result = verifyDocument(
    "sijil_ssm.jpeg",
    "sijil_ssm",
    [
        "nama_perniagaan" => "DFG TELECOMMUNICATION",
        "no_pendaftaran"  => "MA0127232-D",
    ]
);

echo "Verified: " . ($result["verified"] ? "YES" : "NO") . "\\n";
foreach ($result["fields"] as $name => $info) {
    $status = $info["match"] ? "MATCH" : "MISMATCH";
    echo "  $name: $status (expected={$info['expected']}, got={$info['extracted']})\\n";
}
''', language="php")

elif lang == "C# (.NET)":
    st.code('''
using System.Text.Json;

var apiUrl = "https://your-server.example.com";
var apiKey = "YOUR_API_KEY";

async Task<JsonElement> VerifyDocumentAsync(
    string filePath, string docType, Dictionary<string, string> expectedFields)
{
    using var http = new HttpClient();
    http.DefaultRequestHeaders.Add("X-API-Key", apiKey);

    // 1. Submit
    using var form = new MultipartFormDataContent();
    form.Add(new StreamContent(File.OpenRead(filePath)), "file",
             Path.GetFileName(filePath));
    form.Add(new StringContent(docType), "doc_type");
    form.Add(new StringContent(JsonSerializer.Serialize(expectedFields)),
             "expected_fields");

    var submitResp = await http.PostAsync($"{apiUrl}/api/v1/verify", form);
    submitResp.EnsureSuccessStatusCode();
    var submitJson = JsonSerializer.Deserialize<JsonElement>(
        await submitResp.Content.ReadAsStringAsync());
    var jobId = submitJson.GetProperty("job_id").GetString();
    Console.WriteLine($"Submitted: job_id={jobId}");

    // 2. Poll
    while (true)
    {
        var pollResp = await http.GetAsync($"{apiUrl}/api/v1/jobs/{jobId}");
        pollResp.EnsureSuccessStatusCode();
        var data = JsonSerializer.Deserialize<JsonElement>(
            await pollResp.Content.ReadAsStringAsync());
        var status = data.GetProperty("status").GetString();

        if (status == "done")
            return data.GetProperty("result");
        if (status == "failed")
            throw new Exception($"Job failed: {data.GetProperty("error")}");

        await Task.Delay(3000);
    }
}

// Usage
var result = await VerifyDocumentAsync(
    "sijil_ssm.jpeg",
    "sijil_ssm",
    new Dictionary<string, string>
    {
        ["nama_perniagaan"] = "DFG TELECOMMUNICATION",
        ["no_pendaftaran"]  = "MA0127232-D",
    }
);

Console.WriteLine($"Verified: {result.GetProperty("verified")}");
foreach (var field in result.GetProperty("fields").EnumerateObject())
{
    var match = field.Value.GetProperty("match").GetBoolean() ? "MATCH" : "MISMATCH";
    var expected = field.Value.GetProperty("expected").GetString();
    var extracted = field.Value.GetProperty("extracted").GetString();
    Console.WriteLine($"  {field.Name}: {match} (expected={expected}, got={extracted})");
}
''', language="csharp")

elif lang == "JavaScript (Node.js)":
    st.code('''
const fs = require("fs");
const FormData = require("form-data");
const axios = require("axios");

const API_URL = "https://your-server.example.com";
const API_KEY = "YOUR_API_KEY";

async function verifyDocument(filePath, docType, expectedFields) {
  // 1. Submit
  const form = new FormData();
  form.append("file", fs.createReadStream(filePath));
  form.append("doc_type", docType);
  form.append("expected_fields", JSON.stringify(expectedFields));

  const submitResp = await axios.post(`${API_URL}/api/v1/verify`, form, {
    headers: { "X-API-Key": API_KEY, ...form.getHeaders() },
  });
  const jobId = submitResp.data.job_id;
  console.log(`Submitted: job_id=${jobId}`);

  // 2. Poll
  while (true) {
    const pollResp = await axios.get(`${API_URL}/api/v1/jobs/${jobId}`, {
      headers: { "X-API-Key": API_KEY },
    });
    const data = pollResp.data;

    if (data.status === "done") return data.result;
    if (data.status === "failed") throw new Error(`Job failed: ${data.error}`);

    await new Promise((r) => setTimeout(r, 3000));
  }
}

// Usage
(async () => {
  const result = await verifyDocument("sijil_ssm.jpeg", "sijil_ssm", {
    nama_perniagaan: "DFG TELECOMMUNICATION",
    no_pendaftaran: "MA0127232-D",
  });

  console.log(`Verified: ${result.verified}`);
  for (const [name, info] of Object.entries(result.fields)) {
    const status = info.match ? "MATCH" : "MISMATCH";
    console.log(`  ${name}: ${status} (expected=${info.expected}, got=${info.extracted})`);
  }
})();
''', language="javascript")

elif lang == "Java":
    st.code('''
import java.io.*;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import com.google.gson.*;

public class OcrVerify {
    static final String API_URL = "https://your-server.example.com";
    static final String API_KEY = "YOUR_API_KEY";

    public static JsonObject verifyDocument(
            String filePath, String docType, JsonObject expectedFields)
            throws Exception {

        HttpClient client = HttpClient.newHttpClient();
        String boundary = "----FormBoundary" + System.currentTimeMillis();

        // 1. Build multipart body
        byte[] fileBytes = Files.readAllBytes(Path.of(filePath));
        String fileName = Path.of(filePath).getFileName().toString();
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        PrintWriter writer = new PrintWriter(new OutputStreamWriter(body), true);

        writer.append("--").append(boundary).append("\\r\\n");
        writer.append("Content-Disposition: form-data; name=\\"file\\"; ")
              .append("filename=\\"").append(fileName).append("\\"\\r\\n");
        writer.append("Content-Type: image/jpeg\\r\\n\\r\\n").flush();
        body.write(fileBytes);
        writer.append("\\r\\n");

        writer.append("--").append(boundary).append("\\r\\n");
        writer.append("Content-Disposition: form-data; name=\\"doc_type\\"\\r\\n\\r\\n");
        writer.append(docType).append("\\r\\n");

        writer.append("--").append(boundary).append("\\r\\n");
        writer.append("Content-Disposition: form-data; name=\\"expected_fields\\"\\r\\n\\r\\n");
        writer.append(expectedFields.toString()).append("\\r\\n");
        writer.append("--").append(boundary).append("--\\r\\n").flush();

        HttpRequest submitReq = HttpRequest.newBuilder()
                .uri(URI.create(API_URL + "/api/v1/verify"))
                .header("X-API-Key", API_KEY)
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body.toByteArray()))
                .build();

        HttpResponse<String> submitResp =
                client.send(submitReq, HttpResponse.BodyHandlers.ofString());
        String jobId = JsonParser.parseString(submitResp.body())
                .getAsJsonObject().get("job_id").getAsString();
        System.out.println("Submitted: job_id=" + jobId);

        // 2. Poll
        while (true) {
            HttpRequest pollReq = HttpRequest.newBuilder()
                    .uri(URI.create(API_URL + "/api/v1/jobs/" + jobId))
                    .header("X-API-Key", API_KEY)
                    .GET().build();
            HttpResponse<String> pollResp =
                    client.send(pollReq, HttpResponse.BodyHandlers.ofString());
            JsonObject data = JsonParser.parseString(pollResp.body()).getAsJsonObject();
            String status = data.get("status").getAsString();

            if ("done".equals(status))
                return data.getAsJsonObject("result");
            if ("failed".equals(status))
                throw new RuntimeException("Job failed: " + data.get("error"));

            Thread.sleep(3000);
        }
    }

    public static void main(String[] args) throws Exception {
        JsonObject expected = new JsonObject();
        expected.addProperty("nama_perniagaan", "DFG TELECOMMUNICATION");
        expected.addProperty("no_pendaftaran", "MA0127232-D");

        JsonObject result = verifyDocument("sijil_ssm.jpeg", "sijil_ssm", expected);
        System.out.println("Verified: " + result.get("verified").getAsBoolean());
        for (var entry : result.getAsJsonObject("fields").entrySet()) {
            JsonObject info = entry.getValue().getAsJsonObject();
            String match = info.get("match").getAsBoolean() ? "MATCH" : "MISMATCH";
            System.out.printf("  %s: %s (expected=%s, got=%s)%n",
                    entry.getKey(), match,
                    info.get("expected").getAsString(),
                    info.get("extracted").getAsString());
        }
    }
}
''', language="java")

elif lang == "Go":
    st.code('''
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"time"
)

const apiURL = "https://your-server.example.com"
const apiKey = "YOUR_API_KEY"

func verifyDocument(filePath, docType string, expected map[string]string) (map[string]interface{}, error) {
	// 1. Submit
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	file, _ := os.Open(filePath)
	defer file.Close()
	part, _ := writer.CreateFormFile("file", filePath)
	io.Copy(part, file)

	writer.WriteField("doc_type", docType)
	expectedJSON, _ := json.Marshal(expected)
	writer.WriteField("expected_fields", string(expectedJSON))
	writer.Close()

	req, _ := http.NewRequest("POST", apiURL+"/api/v1/verify", body)
	req.Header.Set("X-API-Key", apiKey)
	req.Header.Set("Content-Type", writer.FormDataContentType())

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var submitResult map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&submitResult)
	jobID := submitResult["job_id"].(string)
	fmt.Printf("Submitted: job_id=%s\\n", jobID)

	// 2. Poll
	for {
		req, _ := http.NewRequest("GET", fmt.Sprintf("%s/api/v1/jobs/%s", apiURL, jobID), nil)
		req.Header.Set("X-API-Key", apiKey)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			return nil, err
		}
		var data map[string]interface{}
		json.NewDecoder(resp.Body).Decode(&data)
		resp.Body.Close()

		status := data["status"].(string)
		if status == "done" {
			return data["result"].(map[string]interface{}), nil
		}
		if status == "failed" {
			return nil, fmt.Errorf("job failed: %v", data["error"])
		}
		time.Sleep(3 * time.Second)
	}
}

func main() {
	result, err := verifyDocument("sijil_ssm.jpeg", "sijil_ssm", map[string]string{
		"nama_perniagaan": "DFG TELECOMMUNICATION",
		"no_pendaftaran":  "MA0127232-D",
	})
	if err != nil {
		fmt.Println("Error:", err)
		return
	}
	fmt.Printf("Verified: %v\\n", result["verified"])
	fields := result["fields"].(map[string]interface{})
	for name, v := range fields {
		info := v.(map[string]interface{})
		match := "MISMATCH"
		if info["match"].(bool) {
			match = "MATCH"
		}
		fmt.Printf("  %s: %s (expected=%s, got=%s)\\n",
			name, match, info["expected"], info["extracted"])
	}
}
''', language="go")

elif lang == "cURL (Bash)":
    st.code("""
#!/bin/bash
API_URL="https://your-server.example.com"
API_KEY="YOUR_API_KEY"

# 1. Submit
RESPONSE=$(curl -s -X POST "$API_URL/api/v1/verify" \\
  -H "X-API-Key: $API_KEY" \\
  -F "file=@sijil_ssm.jpeg" \\
  -F "doc_type=sijil_ssm" \\
  -F 'expected_fields={"nama_perniagaan":"DFG TELECOMMUNICATION","no_pendaftaran":"MA0127232-D"}')

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "Submitted: job_id=$JOB_ID"

# 2. Poll
while true; do
  RESULT=$(curl -s "$API_URL/api/v1/jobs/$JOB_ID" -H "X-API-Key: $API_KEY")
  STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")

  if [ "$STATUS" = "done" ]; then
    echo "$RESULT" | python3 -m json.tool
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "FAILED: $RESULT"
    break
  fi

  echo "Status: $STATUS -- waiting..."
  sleep 3
done
""", language="bash")
