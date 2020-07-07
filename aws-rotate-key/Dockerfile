FROM golang:stretch as builder
RUN go get github.com/stefansundin/aws-rotate-key/...

FROM alpine:latest
RUN mkdir /lib64 && ln -s /lib/libc.musl-x86_64.so.1 /lib64/ld-linux-x86-64.so.2 && apk update && apk add ca-certificates && rm -rf /var/cache/apk/*
COPY --from=builder /go/bin/aws-rotate-key .
ENTRYPOINT ["./aws-rotate-key"]
