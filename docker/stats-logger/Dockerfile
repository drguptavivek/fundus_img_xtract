FROM docker:27-cli

WORKDIR /app

COPY docker/stats-logger/logger.sh /logger.sh

RUN chmod +x /logger.sh

ENTRYPOINT ["/logger.sh"]
