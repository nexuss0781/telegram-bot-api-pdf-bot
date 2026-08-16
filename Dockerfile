ARG ALPINE_VERSION=3.21
FROM alpine:${ALPINE_VERSION} AS build

ARG NPROC=2
ARG TELEGRAM_BOT_API_REF=master

ENV CXXFLAGS=""
WORKDIR /usr/src

RUN apk add --no-cache --update \
        alpine-sdk \
        linux-headers \
        git \
        zlib-dev \
        openssl-dev \
        gperf \
        cmake \
    && git clone --depth 1 --recursive \
        --branch "${TELEGRAM_BOT_API_REF}" \
        https://github.com/tdlib/telegram-bot-api.git \
        telegram-bot-api

WORKDIR /usr/src/telegram-bot-api
RUN mkdir -p build \
 && cd build \
 && cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX:PATH=.. .. \
 && cmake --build . --target install -j "${NPROC}" \
 && strip /usr/src/telegram-bot-api/bin/telegram-bot-api

FROM alpine:${ALPINE_VERSION}

ENV TELEGRAM_WORK_DIR="/var/lib/telegram-bot-api" \
    TELEGRAM_TEMP_DIR="/tmp/telegram-bot-api"

RUN apk add --no-cache --update openssl libstdc++
COPY --from=build /usr/src/telegram-bot-api/bin/telegram-bot-api /usr/local/bin/telegram-bot-api
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN addgroup -g 101 -S telegram-bot-api \
 && adduser -S -D -H -u 101 -h ${TELEGRAM_WORK_DIR} -s /sbin/nologin -G telegram-bot-api -g telegram-bot-api telegram-bot-api \
 && chmod +x /docker-entrypoint.sh \
 && mkdir -p ${TELEGRAM_WORK_DIR} ${TELEGRAM_TEMP_DIR} \
 && chown telegram-bot-api:telegram-bot-api ${TELEGRAM_WORK_DIR} ${TELEGRAM_TEMP_DIR}

EXPOSE 8081/tcp 8082/tcp
ENTRYPOINT ["/docker-entrypoint.sh"]
