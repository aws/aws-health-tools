# S3 Multi-Part Object Downloader

This is a tool for downloading multi-part S3 objects, even
when some parts are unavailable.

## Requirements

```bash
pip install boto3
```

---

## Downloading Objects with Missing Parts

Downloads multi-part objects even when some parts are missing or corrupted. Skips failed parts and continues downloading the rest.

**Usage:**

```bash
export AWS_PROFILE=your-profile-name
python s3-download-partial-multiparts.py \
    --bucket your-bucket \
    --key path/to/object.dat \
    --output ./output.dat
```

**If your bucket is in a different region (e.g., me-central-1):**

```bash
python s3-download-partial-multiparts.py \
    --bucket your-bucket \
    --key path/to/object.dat \
    --output ./output.dat \
    --region me-central-1
```

**What you get:**

- During download: A `.PARTIAL` file at the correct size (missing parts are filled with zeros)
- If parts fail: A `.MISSINGRANGES` file listing which byte ranges failed (one line per missing part)
- When complete: The `.PARTIAL` file is renamed to the final name, and `.MISSINGRANGES` is deleted

**File States:**
- `output.dat.PARTIAL` exists → Download in progress or incomplete
- `output.dat` exists (no `.PARTIAL`) → Download complete and verified
- `output.dat.MISSINGRANGES` exists → Details about missing byte ranges

**Example `.MISSINGRANGES` file:**
```
11534336-18874367
50331648-66060287
```

This means parts at those byte ranges couldn't be downloaded and contain zeros instead of data.

**⚠️ Important:** The `.PARTIAL` suffix prevents accidental use of incomplete files. Only files without the `.PARTIAL` suffix are complete and safe to process.

### Retrying Failed Parts

If a download had missing parts, simply run the same command again. The tool will:
- Detect the existing `.PARTIAL` file and `.MISSINGRANGES` file
- **Use HEAD requests to check which parts need retry** (no data transfer, minimal cost)
- **Only retry the failed parts** (skipping parts that already downloaded successfully)
- Update the `.MISSINGRANGES` file with any remaining failures
- **Rename `.PARTIAL` to the final name** and delete `.MISSINGRANGES` when all parts are complete

**Cost Efficiency:** Retry mode uses S3 HEAD requests (not GET) to identify which parts need retry. HEAD requests only retrieve metadata without downloading data, making retries cost-effective even for large objects.

**Example:**
```bash
# First run - parts 3 and 8 fail
python s3-download-partial-multiparts.py --bucket my-bucket --key data.dat --output ./data.dat
# Creates: data.dat.PARTIAL and data.dat.MISSINGRANGES

# Second run - only retries parts 3 and 8
python s3-download-partial-multiparts.py --bucket my-bucket --key data.dat --output ./data.dat
# If successful: renames data.dat.PARTIAL → data.dat, deletes data.dat.MISSINGRANGES
```

**License**

S3-Download-Partial-Multiparts is licensed under the Apache 2.0 License.