ARG RUNTIME_BASE
FROM ${RUNTIME_BASE}
USER root
COPY source/ /opt/fullmag/source/
COPY package/ /opt/fullmag/package/
COPY provenance.json /opt/fullmag/provenance.json
COPY entrypoint.py /opt/fullmag/entrypoint.py
COPY windows_folder_probe.py /opt/fullmag/windows_folder_probe.py
RUN mkdir -p /opt/fullmag/source/.fullmag /state /run/fullmag && chown 65532:65532 /state && \
    ln -s /opt/fullmag/package /opt/fullmag/source/.fullmag/local && \
    chmod -R a+rX /opt/fullmag && \
    chmod 755 /opt/fullmag/package/bin/* && \
    test -x /opt/fullmag/package/bin/fullmag-api
LABEL org.fullmag.runtime="docker-all-gpu-v1"
ENV FULLMAG_REPO_ROOT=/opt/fullmag/source \
    FULLMAG_STATE_ROOT=/state/.fullmag \
    FULLMAG_STATE_DIR=/state/.fullmag \
    HOME=/state \
    FULLMAG_RUNTIME_ROOT=/opt/fullmag/package \
    FULLMAG_WEB_STATIC_DIR=/opt/fullmag/package/web \
    FULLMAG_API_PORT=8081 \
    FULLMAG_PYTHON=/usr/local/bin/python3 \
    PYTHONPATH=/opt/fullmag/source/packages/fullmag-py/src:/opt/fullmag/package \
    PYTHONDONTWRITEBYTECODE=1 \
    LD_LIBRARY_PATH=/opt/fullmag/package/lib:/opt/fullmag-deps/lib:/usr/local/cuda/lib64:${LD_LIBRARY_PATH} \
    FULLMAG_DISABLE_MANAGED_FEM_GPU_RUNTIME=1 \
    FULLMAG_FORCE_LOCAL_FEM_GPU=1 \
    FULLMAG_FEM_EXECUTION=gpu \
    FULLMAG_FDM_EXECUTION=gpu \
    FULLMAG_FEM_REQUIRE_GPU=1 \
    FULLMAG_FEM_REQUIRE_CEED=1 \
    FULLMAG_FEM_MFEM_DEVICE=ceed-cuda:/gpu/cuda/shared \
    FULLMAG_FEM_MESH_CACHE_DIR=/state/.fullmag/mesh-cache \
    CUDA_CACHE_PATH=/state/cuda-cache \
    OMP_NUM_THREADS=16 \
    FULLMAG_CPU_THREADS=16
ENV PATH=/opt/fullmag/source/.fullmag/local/bin:/opt/fullmag-deps/bin:/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin
WORKDIR /state
USER 65532:65532
EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/python3", "/opt/fullmag/entrypoint.py"]
HEALTHCHECK --interval=5s --timeout=3s --start-period=30s --retries=6 \
    CMD /usr/local/bin/python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=2)"
