"""Interpreted BORIS build route guards; no compiler, Docker or provisioning."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from local_runner import boris_cpu as b, build_entrypoint as entry, build_executor as executor, container_client as client

class BorisCpuRouteTests(unittest.TestCase):
    def test_existing_profiles_and_default_admission_unchanged(self):
        self.assertEqual(tuple(client.ALLOWED_PROFILES), ("fem-cpu-release","fem-gpu-release","fdm-cpu-release"))
        self.assertEqual(len(client.SLEPC_MODAL_PROFILES),6)
        self.assertNotIn(b.PROFILE,client.SLEPC_MODAL_PROFILES)
        self.assertEqual(executor.profile_lane(b.PROFILE),("external-reference","cpu"))
        self.assertEqual(entry.required_outputs_for_profile(b.PROFILE),b.OUTPUTS)
        with self.assertRaises(ValueError):executor.dependency_cache_paths(Path("x"),b.PROFILE)
        self.assertEqual(entry.required_outputs_for_profile("fem-cpu-release"),entry.REQUIRED_OUTPUTS)
        self.assertEqual(entry.required_outputs_for_profile("fem-cpu-current-contracts-v1"),entry.BASE_REQUIRED_OUTPUTS)

    def test_opt_in_coexists_with_modal_and_preserves_secret_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            layout={"storage_root":str(Path(temp).resolve())}
            image="sha256:"+"a"*64
            with patch.object(client.coordinator,"docker",side_effect=AssertionError("no Docker")):
                first=client.configure(layout,image_id=image,owner="alice",enable_slepc_modal=True)
                self.assertNotIn(b.PROFILE,first["allowed_profiles"])
                enabled=client.configure(layout,image_id=image,owner="alice",enable_boris_cpu=True)
                self.assertEqual(enabled["allowed_profiles"],list(client.CATALOG_PROFILES))
                preserved=client.configure(layout,image_id=image,owner="alice",enable_current_contracts=True)
                self.assertIn(b.PROFILE,preserved["allowed_profiles"])
            secret=json.loads((Path(temp)/"index/local-runner-container-secret.json").read_text())
            self.assertEqual(secret["allowed_profiles"],preserved["allowed_profiles"])

    def test_missing_activation_fails_before_capsule_read(self):
        from local_runner.container_main import Application
        app=Application.__new__(Application)
        app._assert_submission_ready=lambda:None
        with self.assertRaisesRegex(ValueError,"operator activation"):
            app.submit(dict(worktree_id="wt",source_digest="a"*64,profile=b.PROFILE,
                            operation="build",request_key="test",payload={}))

    def test_exact_overlay_rejects_drift(self):
        cpu=b"#define COMPILECUDA\t1\n#define GRAPHICS 0\n#define PYTHON_EMBEDDING 1\n"
        fixed=b.overlay_flags(cpu,"COMPILECUDA",1,0)
        self.assertIn(b"#define COMPILECUDA 0",fixed)
        for value in (b"#define COMPILECUDA 2\n",b"#define COMPILECUDA 1\n#define COMPILECUDA 1\n"):
            with self.assertRaises(ValueError):b.overlay_flags(value,"COMPILECUDA",1,0)

    def test_fixed_cpp_commands_no_cuda_no_host_build(self):
        command=b.compile_commands(["Boris/Transport.cpp"],compiler="/usr/bin/g++",includes=["-I/usr/include/python3.10"],objects=Path("/workspace/objects"))[0]
        self.assertEqual(command[0],"/usr/bin/g++")
        self.assertIn("-std=c++17",command)
        self.assertFalse(any(b.cuda_toolchain_argument(part) for part in command))
        for bad in ("nvcc","-lcudart","-lnvidia-ml","-I/usr/local/cuda/include"):
            self.assertTrue(b.cuda_toolchain_argument(bad))
        with self.assertRaises(ValueError):b.compile_commands(["../../escape.cpp"],compiler="g++",includes=[],objects=Path("x"))

    def test_source_pin_membership_hash_and_bounds(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"Boris").mkdir();path=root/"Boris/test.cpp";path.write_bytes(b"test")
            files=[dict(path="Boris/test.cpp",size=4,sha256=hashlib.sha256(b"test").hexdigest(),mode="100644")]
            manifest=dict(schema_version="fullmag.boris.image_source.v1",upstream_commit=b.PIN,files=files,source_tree_sha256=hashlib.sha256(b.canonical(files)).hexdigest())
            self.assertEqual(b.verify_source(root,manifest),manifest)
            with self.assertRaises(ValueError):b.verify_source(root,{**manifest,"upstream_commit":"0"*40})
            path.write_bytes(b"bad")
            with self.assertRaises(ValueError):b.verify_source(root,manifest)
            path.write_bytes(b"test");(root/"unexpected").write_bytes(b"x")
            with self.assertRaises(ValueError):b.verify_source(root,manifest)

    def test_missing_image_source_fails_before_toolchain_or_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(b,"SOURCE_MANIFEST",root/"missing"),patch.object(b.subprocess,"run",side_effect=AssertionError("no compiler")):
                with self.assertRaises(ValueError):b.run_build(root,root,{},lambda *a,**k:None)

    def test_fabricated_receipt_missing_members_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):b.validate_outputs(Path(temp),{"profile":b.PROFILE})

class BorisCpuAbiTests(unittest.TestCase):
    # Pure verifier fixture, never compilation or a qualified runtime identity.
    def fixture(self, temp):
        artifacts=Path(temp);root=artifacts/"outputs/boris";root.mkdir(parents=True)
        logs=artifacts/"logs";logs.mkdir()
        (logs/"boris-cpu-abi-observe.stdout.log").write_bytes(b.canonical(b.ABI_FACTS))
        receipt=dict(job_id="a"*32,source_digest="b"*64,image_digest="sha256:"+"c"*64,stages=[])
        proof=dict(compile_flags_sha256="d"*64,cuda_flags_sha256="e"*64,
                   original_source={"files":[dict(path=name,sha256=value) for name,value in b.TYPE_SOURCE_SHA256.items()]})
        (root/"cpu_abi_witness.cpp").write_bytes(b.ABI_SOURCE)
        (root/"cpu_abi_witness").write_bytes(b"synthetic ABI binary; not executable proof")
        (root/"cpu_abi_witness.json").write_bytes(b.canonical(b.abi_binding(receipt,"d"*64,"e"*64,b.ABI_FACTS)))
        proof["cpu_abi_sha256"]={name:b.digest(root/name) for name in b.OUTPUTS if name.startswith("cpu_abi_")}
        prefix=["g++","-c","-Ofast","-std=c++17","-IBorisLib","-IBorisCUDALib","-fopenmp","-Ipython"]
        commands={"boris-cpu-compile-00000":[*prefix,"Boris/Transport.cpp","-o","/workspace/0.o"],
                  "boris-cpu-abi-compile":[*prefix,"Boris/FullmagCpuAbiWitness.cpp","-o","/workspace/abi.o"],
                  "boris-cpu-link":["g++","/workspace/0.o","-fopenmp","-lpython","-ltbb","-lfftw3","-lX11","-o","/workspace/BorisLin"],
                  "boris-cpu-abi-link":["g++","/workspace/abi.o","-fopenmp","-lpython","-ltbb","-lfftw3","-lX11","-o","/workspace/witness"],
                  "boris-cpu-abi-observe":["/workspace/witness"]}
        receipt["stages"]=[dict(name=name,command=command,exit_code=0) for name,command in commands.items()]
        return root,artifacts,receipt,proof,["Boris/Transport.cpp"]

    def test_fixed_source_inspects_actual_transport_types(self):
        for field in ("V[0]", "E[0].x", "S[0].x"):
            self.assertIn(field.encode(),b.ABI_SOURCE)
        self.assertIn(b'#include "MeshBase.h"',b.ABI_SOURCE)
        self.assertNotIn(b"identity_complete",b.ABI_SOURCE)
        self.assertIn("boris-cpu-abi-observe",b.REQUIRED_STAGES)

    def test_observation_rejects_precision_bool_duplicate_and_bounds(self):
        self.assertEqual(b.abi_observation(b.canonical(b.ABI_FACTS)),b.ABI_FACTS)
        for raw in (b.canonical({**b.ABI_FACTS,"double_bytes":4}),
                    b.canonical({**b.ABI_FACTS,"char_bit":True}),
                    b'{"char_bit":8,"char_bit":8}',b"x"*4097,b"[]",b"{}"):
            with self.subTest(raw=raw[:90]),self.assertRaises(ValueError):b.abi_observation(raw)

    def test_pure_fixture_checks_exact_owner_source_and_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            args=self.fixture(temp)
            b.validate_abi_outputs(*args)
            self.assertNotIn("identity_complete",args[2])

    def test_foreign_owner_and_flags_refused(self):
        for key in ("job_id","source_digest","image_digest"):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as temp:
                args=self.fixture(temp);args[2][key]="foreign"
                with self.assertRaisesRegex(ValueError,"owner/flags"):b.validate_abi_outputs(*args)
        with tempfile.TemporaryDirectory() as temp:
            args=self.fixture(temp);args[3]["compile_flags_sha256"]="f"*64
            with self.assertRaisesRegex(ValueError,"owner/flags"):b.validate_abi_outputs(*args)

    def test_stage_missing_duplicate_failed_compiler_linker_and_run_refused(self):
        for case in ("missing","duplicate","failed","compiler","flags","linker","run"):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                args=self.fixture(temp);stages=args[2]["stages"]
                abi=next(x for x in stages if x["name"]=="boris-cpu-abi-compile")
                if case=="missing":stages.remove(abi)
                elif case=="duplicate":stages.append(dict(abi))
                elif case=="failed":abi["exit_code"]=1
                elif case=="compiler":abi["command"][0]="foreign-g++"
                elif case=="flags":abi["command"].insert(1,"-DSINGLEPRECISION=1")
                elif case=="linker":next(x for x in stages if x["name"]=="boris-cpu-abi-link")["command"].insert(2,"-lforeign")
                else:next(x for x in stages if x["name"]=="boris-cpu-abi-observe")["command"]=["/foreign/witness"]
                with self.assertRaises(ValueError):b.validate_abi_outputs(*args)

    def test_tampered_binary_source_typepin_or_oversized_log_refused(self):
        for case in ("binary","source","typepin","log"):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                args=self.fixture(temp)
                if case=="binary":(args[0]/"cpu_abi_witness").write_bytes(b"tamper")
                elif case=="source":
                    (args[0]/"cpu_abi_witness.cpp").write_bytes(b"tamper")
                    args[3]["cpu_abi_sha256"]["cpu_abi_witness.cpp"]=b.digest(args[0]/"cpu_abi_witness.cpp")
                elif case=="typepin":args[3]["original_source"]["files"][0]["sha256"]="f"*64
                else:(args[1]/"logs/boris-cpu-abi-observe.stdout.log").write_bytes(b"x"*4097)
                with self.assertRaises(ValueError):b.validate_abi_outputs(*args)

if __name__=="__main__":unittest.main()
