FROM golang:1.22 AS builder
WORKDIR /workspace
COPY go.mod go.sum ./
RUN go mod download
COPY . .
ARG BUILD_CMD=good
RUN CGO_ENABLED=0 GOOS=linux go build -o /manager ./cmd/${BUILD_CMD}/

FROM gcr.io/distroless/static:nonroot
COPY --from=builder /manager /manager
USER 65532:65532
ENTRYPOINT ["/manager"]
