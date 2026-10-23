FROM golang:1.22-alpine AS builder

WORKDIR /app

COPY go.mod ./
COPY main.go ./

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o ledger_bin main.go

FROM alpine:3.19

WORKDIR /app
COPY --from=builder /app/ledger_bin /app/ledger_bin

ENV LEDGER_PORT=8081
EXPOSE 8081

CMD ["/app/ledger_bin"]
