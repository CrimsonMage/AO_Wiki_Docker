# AO Wiki: public image. The AO bots' recipes, guides and datasets (GPL-3.0), the game's
# item names and its own recipe texts, searchable offline. AO-Universe guides are NOT in this image (see
# README, "AO-Universe guides"); Dockerfile.full adds them.
#
#   docker build -t ao-wiki .
#   docker run --rm -p 8080:8080 ao-wiki        -> http://localhost:8080
FROM python:3.12.7-slim AS build
WORKDIR /src
COPY build/ build/
COPY data/recipes/ data/recipes/
COPY data/items.tsv data/item_texts.json data/
COPY data/nadybot/ data/nadybot/
RUN python3 -I build/build_db.py /src/archive.sqlite && python3 -I build/verify.py /src/archive.sqlite

FROM python:3.12.7-slim
LABEL org.opencontainers.image.title="AO Wiki" \
      org.opencontainers.image.description="Offline Anarchy Online wiki: recipes, guides and the bot datasets" \
      org.opencontainers.image.licenses="Unlicense AND GPL-3.0-only"
RUN useradd --system --uid 10001 archive
WORKDIR /app
COPY app/ /app/
COPY LICENSE README.md /app/
COPY data/recipes/LICENSE /app/LICENSE-GPL-3.0
COPY data/recipes/SOURCE.md /app/SOURCE-recipes.md
COPY data/nadybot/SOURCE.md /app/SOURCE-datasets.md
COPY --from=build /src/archive.sqlite /app/archive.sqlite
# media: item icons, zone maps (+ index.json), planet maps
COPY data/icons/ /app/media/icons/
COPY data/maps/ /app/media/maps/
COPY data/planet/ /app/media/planet/
USER archive
ENV ARCHIVE_DB=/app/archive.sqlite ARCHIVE_MEDIA=/app/media PORT=8080 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz').status == 200 else 1)"
CMD ["python3", "-I", "/app/server.py"]
