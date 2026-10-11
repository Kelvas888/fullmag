"""Fixed BORIS CPU build contract; no caller-selected commands or source mounts."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import uuid

PROFILE = "boris-cpu-v1"
PIN = "048503d2ca6475e91b073eb1762ecf9d3634c3e1"
SOURCE_ROOT = Path("/opt/fullmag-boris/source")
SOURCE_MANIFEST = Path("/opt/fullmag-boris/source_manifest.json")
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_FILES = 20000
OUTPUTS = ("BorisLin", "source_manifest.json", "compile_flags.h", "cuda_flags.h",
           "cpu_abi_witness.cpp", "cpu_abi_witness", "cpu_abi_witness.json")
REQUIRED_STAGES = ("boris-cpu-link", "boris-binary-inspect",
                   "boris-cpu-abi-compile", "boris-cpu-abi-link", "boris-cpu-abi-observe")


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def digest(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("BORIS member is not a regular file")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_member(root, name):
    if not isinstance(name, str) or not name or "\\" in name or "\0" in name:
        raise ValueError("invalid BORIS source path")
    parts = PurePosixPath(name)
    if parts.is_absolute() or any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError("escaping BORIS source path")
    path = root.joinpath(*parts.parts)
    if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise ValueError("BORIS source symlink")
    return path


def verify_source(root, manifest):
    if set(manifest) != {"schema_version", "upstream_commit", "files", "source_tree_sha256"}:
        raise ValueError("invalid BORIS source manifest fields")
    files = manifest["files"]
    if manifest["schema_version"] != "fullmag.boris.image_source.v1" or manifest["upstream_commit"] != PIN:
        raise ValueError("BORIS upstream pin mismatch")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("BORIS source count exceeds bound")
    if hashlib.sha256(canonical(files)).hexdigest() != manifest["source_tree_sha256"]:
        raise ValueError("BORIS source tree identity mismatch")
    total = 0
    names = []
    for entry in files:
        if set(entry) != {"path", "size", "sha256", "mode"} or type(entry["size"]) is not int or entry["size"] < 0:
            raise ValueError("invalid BORIS source entry")
        if entry["mode"] not in ("100644", "100755"):
            raise ValueError("unsupported BORIS source mode")
        path = safe_member(root, entry["path"])
        names.append(entry["path"])
        total += entry["size"]
        if total > MAX_SOURCE_BYTES or path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise ValueError("BORIS source byte identity mismatch or bound exceeded")
    if names != sorted(set(names)):
        raise ValueError("BORIS source order/uniqueness mismatch")
    actual = []
    for base, directories, files_here in os.walk(root, followlinks=False):
        if any((Path(base)/n).is_symlink() for n in directories):
            raise ValueError("BORIS source directory symlink")
        actual.extend((Path(base)/n).relative_to(root).as_posix() for n in files_here)
    if sorted(actual) != names:
        raise ValueError("BORIS source membership mismatch")
    return manifest


def overlay_flags(raw, name, expected, replacement):
    pattern = rb"(?m)^#define[ \t]+" + name.encode() + rb"[ \t]+" + str(expected).encode() + rb"[ \t]*\r?$"
    changed, count = re.subn(pattern, ("#define " + name + " " + str(replacement)).encode(), raw)
    if count != 1:
        raise ValueError("BORIS CPU overlay flag drift: " + name)
    return changed


def cuda_toolchain_argument(value):
    # BorisCUDALib contains shared source headers; guarded CUDA.cpp translation
    # units also exist in CPU builds. Reject toolchain/libs, not source names.
    text=value.lower().replace("\\","/")
    return (Path(text).name == "nvcc" or "/cuda/" in text or "/cuda-" in text
            or any(text.startswith("-l"+name) for name in ("cuda","cufft","nvidia","nvml")))


def compile_commands(cpp_names, *, compiler, includes, objects):
    commands = []
    for ordinal, name in enumerate(cpp_names):
        if re.fullmatch(r"Boris/[A-Za-z0-9_]+\.cpp", name) is None:
            raise ValueError("unexpected BORIS C++ source name")
        commands.append([compiler, "-c", "-Ofast", "-std=c++17", "-IBorisLib", "-IBorisCUDALib",
                         "-fopenmp", *includes, name, "-o", str(objects/f"{ordinal:05d}.o")])
    return commands


def load_manifest(path):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 1024*1024:
        raise ValueError("BORIS image source manifest exceeds bound")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate BORIS manifest key")
            value[key] = item
        return value
    return json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=unique)



TYPE_SOURCE_SHA256 = {
    "Boris/MeshBase.h": "dae9c79545f49b1704038a9152f331a4c5addb7b43a60a613710928440a36636",
    "BorisLib/Types_VAL.h": "1602c65945d070272f47b0aacfddb754523b12deb64bf6c71fb9097859cd5bfe",
}
ABI_FACTS = {"char_bit": 8, "double_bytes": 8, "radix": 2, "digits": 53, "max_exponent": 1024}
ABI_SOURCE = r'''#include <climits>
#include <iostream>
#include <limits>
#include <type_traits>
#include <utility>
#include "MeshBase.h"
template<class T> using Scalar = std::remove_cv_t<std::remove_reference_t<T>>;
static_assert(std::is_same_v<Scalar<decltype(std::declval<MeshBase>().V[0])>, double>);
static_assert(std::is_same_v<Scalar<decltype(std::declval<MeshBase>().E[0].x)>, double>);
static_assert(std::is_same_v<Scalar<decltype(std::declval<MeshBase>().S[0].x)>, double>);
static_assert(std::is_same_v<Scalar<decltype(std::declval<DBL3>().x)>, double>);
static_assert(CHAR_BIT == 8 && sizeof(double) == 8);
static_assert(std::numeric_limits<double>::radix == 2);
static_assert(std::numeric_limits<double>::digits == 53);
static_assert(std::numeric_limits<double>::max_exponent == 1024);
int main() {
    std::cout << "{\"char_bit\":" << CHAR_BIT
              << ",\"double_bytes\":" << sizeof(double)
              << ",\"radix\":" << std::numeric_limits<double>::radix
              << ",\"digits\":" << std::numeric_limits<double>::digits
              << ",\"max_exponent\":" << std::numeric_limits<double>::max_exponent << "}\n";
}
'''.encode("utf-8")


def abi_observation(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 4096:
        raise ValueError("BORIS ABI observation exceeds bound")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate BORIS ABI fact")
            result[key] = value
        return result
    facts = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(facts, dict) or facts != ABI_FACTS or any(type(v) is not int for v in facts.values()):
        raise ValueError("BORIS CPU ABI is not binary64")
    return facts



def read_abi_log(path):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 4096:
        raise ValueError("BORIS ABI observation exceeds bound")
    with path.open("rb") as stream:
        return abi_observation(stream.read(4097))


def abi_binding(receipt, cpu_hash, cuda_hash, facts):
    return dict(schema_version="fullmag.boris.cpu_abi.v1", job_id=receipt["job_id"],
                capsule_digest=receipt["source_digest"], image_digest=receipt["image_digest"],
                compile_flags_sha256=cpu_hash, cuda_flags_sha256=cuda_hash,
                type_source_sha256=TYPE_SOURCE_SHA256, facts=facts)


def run_build(workspace, artifacts, receipt, run_stage):
    """Called only from the operator-pinned trusted entrypoint for PROFILE."""
    manifest = verify_source(SOURCE_ROOT, load_manifest(SOURCE_MANIFEST))
    for name, expected in TYPE_SOURCE_SHA256.items():
        if digest(SOURCE_ROOT/name) != expected:
            raise ValueError("BORIS CPU type source drift")
    source = workspace/"boris-cpu-source"
    shutil.copytree(SOURCE_ROOT, source, copy_function=shutil.copyfile)
    old_cpu = (source/"Boris/CompileFlags.h").read_bytes()
    cpu = overlay_flags(old_cpu, "COMPILECUDA", 1, 0)
    # Keep embedding for the existing public BORIS smoke scripts.
    for name, value in (("GRAPHICS",0),("PYTHON_EMBEDDING",1)):
        overlay_flags(cpu, name, value, value)
    old_cuda = (source/"BorisCUDALib/cuBLib_Flags.h").read_bytes()
    cuda = overlay_flags(old_cuda, "SINGLEPRECISION", 1, 0)
    cuda = overlay_flags(cuda, "COMPILE_NVML_CODE", 0, 0)
    (source/"Boris/CompileFlags.h").write_bytes(cpu)
    (source/"BorisCUDALib/cuBLib_Flags.h").write_bytes(cuda)
    compiler = shutil.which("g++")
    config = shutil.which("python3-config")
    inspector = shutil.which("readelf")
    if not compiler or not config or not inspector:
        raise ValueError("BORIS CPU requires installed g++, Python embed dev and readelf in pinned image")
    def flags(option):
        result = subprocess.run([config, *option], capture_output=True, text=True, check=True, timeout=30)
        values = result.stdout.split()
        if any(cuda_toolchain_argument(value) for value in values):
            raise ValueError("BORIS Python toolchain unexpectedly includes CUDA")
        return values
    objects = workspace/"boris-cpu-objects"
    objects.mkdir()
    cpp = [e["path"] for e in manifest["files"] if re.fullmatch(r"Boris/[A-Za-z0-9_]+\.cpp",e["path"])]
    if not cpp:
        raise ValueError("BORIS C++ source list empty")
    includes=flags(["--includes"])
    if not any(arg.startswith("-I") and (Path(arg[2:])/"Python.h").is_file() for arg in includes):
        raise ValueError("BORIS pinned image lacks Python development headers")
    for library in ("libfftw3.so","libX11.so","libtbb.so"):
        installed=subprocess.check_output([compiler,"-print-file-name="+library],timeout=30).decode().strip()
        if installed==library or not Path(installed).is_file():
            raise ValueError("BORIS pinned image lacks installed development library: "+library)
    commands = compile_commands(cpp, compiler=compiler, includes=includes, objects=objects)
    receipt["toolchain"] = {"g++": subprocess.check_output([compiler,"--version"],timeout=30).decode("utf-8")[:4096],
                            "python": subprocess.check_output(["python3","--version"],timeout=30).decode("utf-8")[:4096],
                            "python_config":config,"readelf":inspector}
    environment = dict(os.environ)
    # Compiler/library search is image-owned, never inherited from job overrides.
    for name in ("CPATH","CPLUS_INCLUDE_PATH","LIBRARY_PATH","LD_PRELOAD"):
        environment.pop(name,None)
    def stage(name, command):
        record = run_stage(name,command,workspace=source,artifacts=artifacts,environment=environment)
        receipt["stages"].append(record)
        if record["exit_code"] != 0:
            raise ValueError("BORIS managed stage failed: " + name)
    for ordinal, command in enumerate(commands):
        stage(f"boris-cpu-compile-{ordinal:05d}", command)
    link_flags = ["-fopenmp", *flags(["--embed","--ldflags"]), "-ltbb", "-lfftw3", "-lX11"]
    witness_source = source/"Boris/FullmagCpuAbiWitness.cpp"
    witness_source.write_bytes(ABI_SOURCE)
    witness_compile = compile_commands(["Boris/FullmagCpuAbiWitness.cpp"], compiler=compiler,
                                       includes=includes, objects=objects/"abi")[0]
    (objects/"abi").mkdir()
    witness_binary = source/"cpu_abi_witness"
    stage("boris-cpu-abi-compile", witness_compile)
    stage("boris-cpu-abi-link", [compiler, witness_compile[-1], *link_flags, "-o", str(witness_binary)])
    if not 0 < witness_binary.stat().st_size <= 16*1024*1024:
        raise ValueError("BORIS ABI executable exceeds bound")
    stage("boris-cpu-abi-observe", [str(witness_binary)])
    facts = read_abi_log(artifacts/"logs/boris-cpu-abi-observe.stdout.log")
    binary = source/"BorisLin"
    stage("boris-cpu-link", [compiler,*[c[-1] for c in commands],*link_flags,"-o",str(binary)])
    stage("boris-binary-inspect", [inspector,"-d",str(binary)])
    dynamic = (artifacts/"logs"/"boris-binary-inspect.stdout.log").read_text(encoding="utf-8")
    if re.search(r"NEEDED.*(?:cuda|cufft|nvidia|nvml)",dynamic,re.I):
        raise ValueError("BORIS CPU binary depends on CUDA/NVML")
    destination = artifacts/"outputs"/"boris"
    destination.mkdir(parents=True)
    shutil.copyfile(binary,destination/"BorisLin")
    (destination/"BorisLin").chmod(0o755)
    (destination/"compile_flags.h").write_bytes(cpu)
    (destination/"cuda_flags.h").write_bytes(cuda)
    (destination/"cpu_abi_witness.cpp").write_bytes(ABI_SOURCE)
    shutil.copyfile(witness_binary,destination/"cpu_abi_witness")
    (destination/"cpu_abi_witness").chmod(0o755)
    observed = abi_binding(receipt,digest(destination/"compile_flags.h"),digest(destination/"cuda_flags.h"),facts)
    (destination/"cpu_abi_witness.json").write_bytes(canonical(observed))
    proof = {"schema_version":"fullmag.boris.source.v2","upstream_commit":PIN,
             "original_source":manifest,"binary_sha256":digest(destination/"BorisLin"),
             "compile_flags_sha256":digest(destination/"compile_flags.h"),
             "cuda_flags_sha256":digest(destination/"cuda_flags.h"),
             "overlay_original_sha256":[hashlib.sha256(old_cpu).hexdigest(),hashlib.sha256(old_cuda).hexdigest()],
             "profile":PROFILE,"job_id":receipt["job_id"],"capsule_digest":receipt["source_digest"],
             "image_digest":receipt["image_digest"],"compile_source_count":len(cpp),
             "precision_claim":"cpu_double_requires_runtime_verification","qualification":"NOT VERIFIED",
             "cpu_abi_sha256":{name:digest(destination/name) for name in OUTPUTS if name.startswith("cpu_abi_")}}
    (destination/"source_manifest.json").write_bytes(canonical(proof))
    receipt["boris_build_proof"] = proof


def validate_outputs(artifacts, receipt):
    """Coordinator-side binding; ordinary Fullmag receipt admission is untouched."""
    root = artifacts/"outputs"/"boris"
    value = load_manifest(root/"source_manifest.json")
    if value != receipt.get("boris_build_proof") or value.get("schema_version") != "fullmag.boris.source.v2":
        raise ValueError("BORIS source receipt mismatch")
    for name, expected in (("upstream_commit",PIN),("profile",PROFILE),("qualification","NOT VERIFIED")):
        if value.get(name) != expected:
            raise ValueError("BORIS receipt pin mismatch")
    for key in ("job_id","image_digest"):
        if value.get(key) != receipt.get(key):
            raise ValueError("BORIS receipt owner mismatch")
    if value.get("capsule_digest") != receipt.get("source_digest"):
        raise ValueError("BORIS capsule mismatch")
    for filename, key in (("BorisLin","binary_sha256"),("compile_flags.h","compile_flags_sha256"),("cuda_flags.h","cuda_flags_sha256")):
        if digest(root/filename) != value.get(key):
            raise ValueError("BORIS output hash mismatch")
    cpu=(root/"compile_flags.h").read_bytes();cuda=(root/"cuda_flags.h").read_bytes()
    for name in ("COMPILECUDA","GRAPHICS"):
        overlay_flags(cpu,name,0,0)
    overlay_flags(cpu,"PYTHON_EMBEDDING",1,1)
    for name in ("SINGLEPRECISION","COMPILE_NVML_CODE"):
        overlay_flags(cuda,name,0,0)
    original=value.get("original_source")
    if not isinstance(original,dict) or original.get("schema_version")!="fullmag.boris.image_source.v1" or original.get("upstream_commit")!=PIN:
        raise ValueError("BORIS original source identity absent")
    files=original.get("files")
    if not isinstance(files,list) or not 1<=len(files)<=MAX_FILES or hashlib.sha256(canonical(files)).hexdigest()!=original.get("source_tree_sha256"):
        raise ValueError("BORIS original source manifest mismatch")
    names=[e.get("path") for e in files]
    if any(not isinstance(name,str) for name in names) or names!=sorted(set(names)):
        raise ValueError("BORIS original source order mismatch")
    cpp=[name for name in names if re.fullmatch(r"Boris/[A-Za-z0-9_]+\.cpp",name)]
    count=value.get("compile_source_count")
    if type(count) is not int or not 1 <= count <= MAX_FILES:
        raise ValueError("BORIS compile source count invalid")
    if count!=len(cpp):
        raise ValueError("BORIS compile count does not match pinned source")
    required = [*REQUIRED_STAGES,*[f"boris-cpu-compile-{i:05d}" for i in range(count)]]
    stages=receipt.get("stages",[])
    if any(sum(s.get("name")==name and s.get("exit_code")==0 for s in stages)!=1 for name in required):
        raise ValueError("BORIS required stages missing/duplicated")
    for ordinal,name in enumerate(cpp):
        record=next(s for s in stages if s.get("name")==f"boris-cpu-compile-{ordinal:05d}")
        command=record.get("command",[])
        if name not in command or "-Ofast" not in command or "-std=c++17" not in command or "-fopenmp" not in command:
            raise ValueError("BORIS compile command/source mismatch")
        if any(cuda_toolchain_argument(arg) for arg in command):
            raise ValueError("BORIS CPU command contains CUDA")
    validate_abi_outputs(root, artifacts, receipt, value, cpp)
    dynamic=(artifacts/"logs"/"boris-binary-inspect.stdout.log").read_text(encoding="utf-8")
    if re.search(r"NEEDED.*(?:cuda|cufft|nvidia|nvml)",dynamic,re.I):
        raise ValueError("BORIS output depends on CUDA/NVML")



def validate_abi_outputs(root, artifacts, receipt, proof, cpp):
    for name, bound in (("cpu_abi_witness.cpp",8192),("cpu_abi_witness",16*1024*1024),("cpu_abi_witness.json",4096)):
        path = root/name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= bound:
            raise ValueError("BORIS ABI artifact exceeds bound")
        if digest(path) != proof.get("cpu_abi_sha256",{}).get(name):
            raise ValueError("BORIS ABI artifact hash mismatch")
    if (root/"cpu_abi_witness.cpp").read_bytes() != ABI_SOURCE:
        raise ValueError("BORIS ABI witness source mismatch")
    observed = load_manifest(root/"cpu_abi_witness.json")
    facts = read_abi_log(artifacts/"logs/boris-cpu-abi-observe.stdout.log")
    if observed != abi_binding(receipt,proof["compile_flags_sha256"],proof["cuda_flags_sha256"],facts):
        raise ValueError("BORIS ABI observation owner/flags mismatch")
    sources = {entry["path"]:entry["sha256"] for entry in proof["original_source"]["files"]}
    if any(sources.get(name) != expected for name,expected in TYPE_SOURCE_SHA256.items()):
        raise ValueError("BORIS ABI type source pin mismatch")
    stages = receipt["stages"]
    def command(name):
        matches=[s for s in stages if s.get("name")==name]
        if len(matches)!=1 or matches[0].get("exit_code")!=0:
            raise ValueError("BORIS ABI stage missing or duplicated")
        result=matches[0].get("command")
        if not isinstance(result,list) or not result or any(not isinstance(v,str) for v in result):
            raise ValueError("BORIS ABI command invalid")
        return result
    witness = command("boris-cpu-abi-compile")
    if len(witness)<4 or witness[-3:-1] != ["Boris/FullmagCpuAbiWitness.cpp","-o"]:
        raise ValueError("BORIS ABI compile source mismatch")
    for ordinal,name in enumerate(cpp):
        actual=command(f"boris-cpu-compile-{ordinal:05d}")
        if actual[-3:-1] != [name,"-o"] or actual[:-3] != witness[:-3]:
            raise ValueError("BORIS ABI compiler/flags differ from solver")
    solver_link=command("boris-cpu-link")
    abi_link=command("boris-cpu-abi-link")
    if (len(solver_link)<len(cpp)+4 or solver_link[0]!=witness[0] or solver_link[-2]!="-o" or len(abi_link)<4
            or abi_link[:2]!=[witness[0],witness[-1]] or abi_link[-2]!="-o"
            or solver_link[len(cpp)+1:-2] != abi_link[2:-2]
            or command("boris-cpu-abi-observe") != [abi_link[-1]]):
        raise ValueError("BORIS ABI linker/run differ from solver")


def prepare_context(repo, boris_source, image):
    # Direct script invocation needs the canonical scripts module root.
    if __package__ in (None, ""):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from fullmag_storage import resolve_layout, validate_path
    if re.fullmatch(r"sha256:[a-f0-9]{64}",image) is None:
        raise ValueError("immutable installed toolchain image ID required")
    root=boris_source.resolve(strict=True)
    if root.is_symlink():
        raise ValueError("BORIS checkout symlink")
    def git(*args):
        return subprocess.check_output(["git","--no-optional-locks","-C",str(root),*args])
    if git("rev-parse","HEAD").decode().strip()!=PIN or git("status","--porcelain","--untracked-files=all").strip():
        raise ValueError("BORIS source must be clean exact pinned checkout")
    layout=resolve_layout(repo,"windows-native")
    storage=Path(layout["storage_root"])
    context=validate_path(storage/"tmp"/("boris-cpu-image-"+uuid.uuid4().hex),storage)
    context.mkdir(parents=True)
    entries=[];total=0
    for item in git("ls-tree","-r","-z","HEAD").split(b"\0"):
        if not item:continue
        metadata,name=item.split(b"\t",1);mode,kind,oid=metadata.split()
        if kind!=b"blob" or mode not in (b"100644",b"100755"):
            raise ValueError("BORIS source gitlink/symlink unsupported")
        name=name.decode("utf-8");path=safe_member(root,name)
        size=path.stat().st_size;total+=size
        if total>MAX_SOURCE_BYTES or len(entries)>=MAX_FILES:
            raise ValueError("BORIS context source bound exceeded")
        data=path.read_bytes()
        if hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()!=oid.decode():
            raise ValueError("BORIS source changed during capture")
        target=context/"source"/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        entries.append(dict(path=name,size=len(data),sha256=hashlib.sha256(data).hexdigest(),mode=mode.decode()))
    entries.sort(key=lambda e:e["path"])
    manifest=dict(schema_version="fullmag.boris.image_source.v1",upstream_commit=PIN,files=entries,
                  source_tree_sha256=hashlib.sha256(canonical(entries)).hexdigest())
    verify_source(context/"source",manifest)
    (context/"source_manifest.json").write_bytes(canonical(manifest))
    shutil.copyfile(Path(__file__).parent/"Dockerfile.boris-cpu",context/"Dockerfile")
    print(json.dumps(dict(context=str(context),toolchain_image=image,source_tree_sha256=manifest["source_tree_sha256"],qualification="NOT VERIFIED")))
    return context


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepare-image-context",choices=("prepare-image-context",))
    parser.add_argument("--repo-root",type=Path,required=True)
    parser.add_argument("--boris-source",type=Path,required=True)
    parser.add_argument("--toolchain-image",required=True)
    args=parser.parse_args()
    prepare_context(args.repo_root,args.boris_source,args.toolchain_image)

if __name__=="__main__":
    main()
