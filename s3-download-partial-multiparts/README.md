# S3 Multi-Part Object Downloader

This is a tool for downloading multi-part S3 objects, even when some parts are
unavailable.

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
python s3-download-partial-multipart.py \
    --bucket your-bucket \
    --key path/to/object.dat \
    --output ./output.dat
```

**If your bucket is in a different region (e.g., me-central-1):**

```bash
python s3-download-partial-multipart.py \
    --bucket your-bucket \
    --key path/to/object.dat \
    --output ./output.dat \
    --region me-central-1
```

**What you get:**

- Output file at the correct size (missing parts are filled with zeros)
- A `.MISSINGRANGES` file listing which byte ranges failed (one line per missing part)

**Example `.MISSINGRANGES` file:**
```
11534336-18874367
50331648-66060287
```

This means parts at those byte ranges couldn't be downloaded and contain zeros instead of data.

### Retrying Failed Parts

If a download had missing parts, simply run the same command again. The tool will:
- Detect the existing output file and `.MISSINGRANGES` file
- **Only retry the failed parts** (skipping parts that already downloaded successfully)
- Update the `.MISSINGRANGES` file with any remaining failures
- **Delete the `.MISSINGRANGES` file** if all parts are now complete

**Example:**
```bash
# First run - parts 3 and 8 fail
python s3-download-partial-multipart.py --bucket my-bucket --key data.dat --output ./data.dat
# Creates: data.dat and data.dat.MISSINGRANGES

# Second run - only retries parts 3 and 8
python s3-download-partial-multipart.py --bucket my-bucket --key data.dat --output ./data.dat
# If successful, deletes data.dat.MISSINGRANGES and file is complete
```
