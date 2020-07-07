## Tool that help to rotate own AWS API IAM keys.

```bash
docker run -v /Users/$USER/.aws/credentials:/root/.aws/credentials quay.io/verygoodsecurity/aws-rotate-key -h
```

Container is based on https://github.com/stefansundin/aws-rotate-key
