FROM postgres:17-alpine@sha256:eee6c6e1b0894fa4fe0075eb054af9fd1cf39a35321c2d4110626cfe506411fb AS hardened

# The upstream entrypoint only needs gosu-compatible user switching. Alpine's
# tiny, packaged su-exec avoids shipping the vulnerable Go runtime embedded in
# upstream gosu while preserving the exact entrypoint invocation contract.
RUN apk add --no-cache su-exec \
    && rm -f /usr/local/bin/gosu \
    && ln -s /sbin/su-exec /usr/local/bin/gosu

# Flatten the resulting filesystem so scanners and registries do not retain
# the deleted gosu binary in a lower image layer.
FROM scratch
COPY --from=hardened / /
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=en_US.utf8 \
    PG_MAJOR=17 \
    PG_VERSION=17.11 \
    PGDATA=/var/lib/postgresql/data
ENTRYPOINT ["docker-entrypoint.sh"]
STOPSIGNAL SIGINT
CMD ["postgres"]
