"""Pinned, offline CPU adapter, imported only after the managed GO gate."""
from pathlib import Path
import os
import sys
import math
import json
from .job_service import canonical
from .run_files import fingerprint
from .training_assets import BASE_MANIFEST

class TrainingPolicyError(BaseException):
    """Cannot be swallowed by upstream best-effort Exception handlers."""


def prepare_environment(root):
    # Called before ML imports. Retain no inherited keys, credentials or integration configuration.
    for name in ("home", "tmp", "config", "cache", "mpl", "runs"):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    from .config import data_root
    platform_root = str(data_root())
    os.environ.clear()
    os.environ.update({"PATH": str(Path(sys.executable).parent) + os.pathsep + "/usr/bin:/bin",
        "PLATFORM_DATA_ROOT": platform_root, "HOME": str(root / "home"), "TMPDIR": str(root / "tmp"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_CACHE_HOME": str(root / "cache"), "YOLO_CONFIG_DIR": str(root / "config"), "MPLCONFIGDIR": str(root / "mpl"),
        "MPLBACKEND": "Agg", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
        "YOLO_OFFLINE": "True", "YOLO_AUTOINSTALL": "False", "ULTRALYTICS_SAFE_LOAD": "True", "CUDA_VISIBLE_DEVICES": "",
        "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "NUMEXPR_NUM_THREADS": "2",
        "NUMEXPR_MAX_THREADS": "2", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
    sys.dont_write_bytecode = True
    settings = {"settings_version": "0.0.8", "datasets_dir": str(root / "dataset"), "weights_dir": str(root),
        "runs_dir": str(root / "runs"), "uuid": "00000000000000000000000000000000", "sync": False, "api_key": "", "openai_api_key": ""}
    settings.update({key: False for key in ("clearml", "comet", "dvc", "mlflow", "raytune", "tensorboard", "wandb", "vscode_msg", "openvino_msg")})
    (root / "config" / "Ultralytics").mkdir(exist_ok=True)
    (root / "config" / "Ultralytics" / "settings.json").write_text(canonical(settings))


def initialize(root, allowed):
    fatal = []
    def fail(reason):
        fatal.append(reason)
        raise TrainingPolicyError(reason)
    def check_write(path):
        if isinstance(path, int): return
        try: value = Path(os.fsdecode(path)).resolve()
        except TypeError: return
        if value != root and root not in value.parents: fail("WRITE_OUTSIDE_RUN")
    def audit(event, args):
        if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.sendto", "socket.bind"}: fail("NETWORK_ATTEMPT")
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.posix_spawnp", "os.exec", "os.fork", "os.forkpty", "os.spawn"}: fail("SUBPROCESS_ATTEMPT")
        if event == "open":
            path, mode, flags = args
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)): check_write(path)
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.chown", "os.truncate", "os.utime"}: check_write(args[0])
        if event in {"os.rename", "os.link", "os.symlink"}: check_write(args[0]); check_write(args[1])
    sys.addaudithook(audit)
    import torch, torchvision, numpy, cv2, ultralytics
    from ultralytics import YOLO
    from ultralytics.utils import SETTINGS, AUTOINSTALL, ONLINE, SAFE_LOAD
    import ultralytics.utils as uu
    import ultralytics.utils.torch_utils as tu
    import ultralytics.utils.checks as checks
    import ultralytics.data.utils as du
    import ultralytics.data.base as db
    import ultralytics.data.dataset as dd
    from ultralytics.nn.tasks import _SafeLoad, DetectionModel
    from ultralytics.nn.modules import block as block_module, conv as conv_module, head as head_module
    if torch.__version__ != "2.15.0+cpu" or torchvision.__version__ != "0.29.2+cpu" or ultralytics.__version__ != "8.4.202" or sys.platform != "linux": fail("RUNTIME_VERSION_MISMATCH")
    if torch.version.cuda is not None or torch.version.hip is not None or torch.cuda.is_available(): fail("DEVICE_NOT_VERIFIED")
    if ONLINE or AUTOINSTALL or not SAFE_LOAD or not _SafeLoad.SUPPORTED or SETTINGS["sync"] or SETTINGS["api_key"] or SETTINGS["openai_api_key"] or any(SETTINGS[k] for k in ("clearml", "comet", "dvc", "mlflow", "raytune", "tensorboard", "wandb")): fail("RUNTIME_SETTINGS_INVALID")
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    cv2.setNumThreads(2)
    for module in (uu, tu, db, dd): module.NUM_THREADS = 2
    # This fixed adapter never plots. The pinned dataset checker otherwise downloads a font.
    def no_plot_font(*args, **kwargs): return None
    checks.check_font = no_plot_font
    du.check_font = no_plot_font
    fixed_globals = {
        'torch.nn.modules.activation.SiLU': torch.nn.SiLU,
        'torch.nn.modules.batchnorm.BatchNorm2d': torch.nn.BatchNorm2d,
        'torch.nn.modules.container.ModuleList': torch.nn.ModuleList,
        'torch.nn.modules.container.Sequential': torch.nn.Sequential,
        'torch.nn.modules.conv.Conv2d': torch.nn.Conv2d,
        'torch.nn.modules.linear.Identity': torch.nn.Identity,
        'torch.nn.modules.pooling.MaxPool2d': torch.nn.MaxPool2d,
        'torch.nn.modules.upsampling.Upsample': torch.nn.Upsample,
        'ultralytics.nn.modules.block.Attention': block_module.Attention,
        'ultralytics.nn.modules.block.Bottleneck': block_module.Bottleneck,
        'ultralytics.nn.modules.block.C2PSA': block_module.C2PSA,
        'ultralytics.nn.modules.block.C3k': block_module.C3k,
        'ultralytics.nn.modules.block.C3k2': block_module.C3k2,
        'ultralytics.nn.modules.block.DFL': block_module.DFL,
        'ultralytics.nn.modules.block.PSABlock': block_module.PSABlock,
        'ultralytics.nn.modules.block.SPPF': block_module.SPPF,
        'ultralytics.nn.modules.conv.Concat': conv_module.Concat,
        'ultralytics.nn.modules.conv.Conv': conv_module.Conv,
        'ultralytics.nn.modules.conv.DWConv': conv_module.DWConv,
        'ultralytics.nn.modules.head.Detect': head_module.Detect,
        'ultralytics.nn.tasks.DetectionModel': DetectionModel,
        'ultralytics.utils.IterableSimpleNamespace': uu.IterableSimpleNamespace,
        'numpy.dtype': numpy.dtype,
        'numpy.core.multiarray.scalar': numpy._core.multiarray.scalar,
        'numpy._core.multiarray.scalar': numpy._core.multiarray.scalar,
    }
    def fixed_register(cls, weight):
        path = Path(weight).resolve()
        if path not in allowed or not path.is_file() or Path(weight).is_symlink(): fail("CHECKPOINT_PATH_INVALID")
        torch.serialization.clear_safe_globals()
        torch.serialization.add_safe_globals([(obj, name) for name, obj in fixed_globals.items()] + [numpy.dtypes.Float64DType])
        if torch.serialization.get_unsafe_globals_in_checkpoint(path): fail("CHECKPOINT_CLASS_REJECTED")
    _SafeLoad.register = classmethod(fixed_register)
    original_load = torch.load
    loads = []
    def local_safe_load(file, *args, **kwargs):
        if not isinstance(file, (str, Path)): fail("CHECKPOINT_PATH_INVALID")
        path = Path(file).resolve()
        if path not in allowed or Path(file).is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024**2: fail("CHECKPOINT_PATH_INVALID")
        if path.name == "yolo11n.pt" and fingerprint(path) != (BASE_MANIFEST["size_bytes"], BASE_MANIFEST["sha256"]): fail("BASE_CHANGED")
        _SafeLoad.register(path)
        kwargs["weights_only"] = True
        loads.append(path.name)
        return original_load(path, *args, **kwargs)
    torch.load = local_safe_load
    return torch, torchvision, YOLO, DetectionModel, fail, fatal, loads


def train(root, params, classes, files, emit):
    prepare_environment(root)
    weights = root / "runs" / "training" / "weights"
    allowed = {root / "yolo11n.pt", weights / "best.pt", weights / "last.pt"}
    torch, torchvision, YOLO, DetectionModel, fail, fatal, loads = initialize(root, allowed)
    from ultralytics.models.yolo.detect import DetectionTrainer
    from ultralytics.utils.torch_utils import unwrap_model
    from ultralytics import __version__ as version
    epochs, steps, active_epoch = [], [], [None]
    final_phase = [False]
    effective = {}
    def finite_state(model):
        for value in model.state_dict().values():
            if isinstance(value, torch.Tensor) and value.is_floating_point():
                if not torch.isfinite(value).all() or not torch.isfinite(value.half()).all(): fail("NONFINITE_MODEL")
    def invariant(trainer):
        if str(trainer.device) != "cpu" or trainer.ddp or trainer.batch_size != params["batch"] or trainer.args.batch != params["batch"] or trainer.epochs != params["epochs"] or trainer.args.resume or trainer.args.optimizer != "SGD" or trainer.args.lr0 != params["learning_rate"]: fail("TRAINING_PARAMETERS_DRIFTED")
    class FixedTrainer(DetectionTrainer):
        def _build_train_pipeline(self):
            if getattr(self, "_oom_retries", 0): fail("TRAINING_OOM")
            return super()._build_train_pipeline()
        def _handle_nan_recovery(self, epoch):
            if self.loss is not None and not torch.isfinite(self.loss).all(): fail("NONFINITE_LOSS")
            if self.fitness is not None and not math.isfinite(float(self.fitness)): fail("NONFINITE_METRIC")
            return False
        def save_model(self):
            invariant(self)
            finite_state(unwrap_model(self.model))
            finite_state(self.ema.ema)
            for value in self.metrics.values():
                if not math.isfinite(float(value)): fail("NONFINITE_METRIC")
            return super().save_model()
        def final_eval(self):
            final_phase[0] = True
            return super().final_eval()
    model = YOLO(str(root / "yolo11n.pt"), task="detect")
    if not isinstance(model.model, DetectionModel): fail("MODEL_STRUCTURE_INVALID")
    def start(trainer):
        invariant(trainer)
        if type(trainer.optimizer) is not torch.optim.SGD: fail("OPTIMIZER_MISMATCH")
        expected = {str((root / "dataset" / entry["path"]).resolve()) for entry in files if entry["path"].startswith("images/train/")}
        expected_val = {str((root / "dataset" / entry["path"]).resolve()) for entry in files if entry["path"].startswith("images/val/")}
        if set(trainer.train_loader.dataset.im_files) != expected or set(trainer.test_loader.dataset.im_files) != expected_val: fail("DATASET_MEMBERSHIP_CHANGED")
        if trainer.data["names"] != dict(enumerate(classes)): fail("DATASET_CLASSES_CHANGED")
        import numpy as np
        for dataset in (trainer.train_loader.dataset, trainer.test_loader.dataset):
            for label in dataset.labels:
                image = Path(label["im_file"])
                relative = image.relative_to(root / "dataset")
                label_path = root / "dataset" / "labels" / Path(*relative.parts[1:]).with_suffix(".txt")
                raw = [list(map(float, line.split())) for line in label_path.read_text().splitlines() if line.strip()]
                expected_labels = np.array(raw, dtype=np.float32).reshape((-1, 5))
                actual = np.concatenate((label["cls"], label["bboxes"]), axis=1)
                if actual.shape != expected_labels.shape or not np.array_equal(actual, expected_labels): fail("DATASET_LABELS_TRANSFORMED")
        for entry in files:
            if entry["path"] != "data.yaml" and fingerprint(root / "dataset" / entry["path"]) != (entry["size_bytes"], entry["sha256"]): fail("DATASET_BYTES_TRANSFORMED")
        effective.update({key: getattr(trainer.args, key) for key in ("optimizer", "lr0", "lrf", "warmup_epochs", "warmup_bias_lr", "warmup_momentum", "momentum", "weight_decay", "nbs", "seed", "batch", "epochs", "imgsz", "device", "workers", "amp", "plots", "cache", "deterministic")})
        trainer.optimizer.register_step_post_hook(lambda *_: steps.append(trainer.epoch))
    def epoch_start(trainer):
        invariant(trainer)
        if trainer.epoch in epochs or trainer.epoch != len(epochs): fail("EPOCH_REPLAY")
        epochs.append(trainer.epoch)
        active_epoch[0] = trainer.epoch
    def epoch_end(trainer):
        invariant(trainer)
        if trainer.loss is not None and not torch.isfinite(trainer.loss).all(): fail("NONFINITE_LOSS")
        finite_state(unwrap_model(trainer.model)); finite_state(trainer.ema.ema)
    def metrics(trainer):
        if final_phase[0]: return
        if active_epoch[0] != trainer.epoch: fail("METRIC_PHASE_INVALID")
        invariant(trainer)
        values = {**trainer.label_loss_items(trainer.tloss, prefix="train"), **trainer.metrics}
        from .training_contract import METRIC_NAMES
        for name in sorted(METRIC_NAMES.intersection(values)):
            value = float(values[name])
            if not math.isfinite(value): fail("NONFINITE_METRIC")
            emit(trainer.epoch + 1, name, value)
        active_epoch[0] = None
    for name, callback in (("on_train_start", start), ("on_train_epoch_start", epoch_start), ("on_train_epoch_end", epoch_end), ("on_fit_epoch_end", metrics)):
        model.add_callback(name, callback)
    # Explicit production defaults, distinct from standalone smoke-only nbs/warmup overrides.
    options = dict(data=str(root / "dataset" / "data.yaml"), epochs=params["epochs"], imgsz=params["imgsz"], batch=params["batch"],
        workers=0, seed=params["seed"], device="cpu", amp=False, plots=False, cache=False, resume=False,
        optimizer="SGD", lr0=params["learning_rate"], lrf=0.01, warmup_epochs=3.0, nbs=64,
        deterministic=True, project=str(root / "runs"), name="training", exist_ok=False, save=True, save_period=-1,
        val=True, verbose=False, compile=False, close_mosaic=0, patience=0)
    model.train(trainer=FixedTrainer, **options)
    if fatal or len(epochs) != params["epochs"] or not steps or active_epoch[0] is not None: fail("TRAINING_INCOMPLETE")
    output = []
    for name in ("best.pt", "last.pt"):
        path = weights / name
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        if checkpoint.get("optimizer") is not None or checkpoint.get("ema") is not None or checkpoint.get("epoch") != -1: fail("CHECKPOINT_NOT_FINALIZED")
        saved_model = checkpoint.get("model")
        if not isinstance(saved_model, DetectionModel): fail("MODEL_STRUCTURE_INVALID")
        safe_args = {key: value for key, value in effective.items() if key in {"optimizer", "lr0", "lrf", "warmup_epochs", "nbs", "seed", "batch", "epochs", "imgsz", "device"}}
        safe_args["task"] = "detect"
        saved_model.args = safe_args.copy()
        if hasattr(saved_model, "pt_path"): del saved_model.pt_path
        if isinstance(saved_model.yaml, dict):
            saved_model.yaml = {key: value for key, value in saved_model.yaml.items() if key != "yaml_file"}
        saved_model.criterion = None
        safe_checkpoint = {"model": saved_model, "ema": None, "optimizer": None, "epoch": -1,
                           "train_args": safe_args, "version": version, "license": "AGPL-3.0"}
        temporary = path.with_suffix(".part")
        torch.save(safe_checkpoint, temporary)
        os.replace(temporary, path)
        before = fingerprint(path)
        loaded = YOLO(str(path), task="detect")
        if not isinstance(loaded.model, DetectionModel) or loaded.names != dict(enumerate(classes)) or loaded.task != "detect" or str(next(loaded.model.parameters()).device) != "cpu": fail("OUTPUT_MODEL_INVALID")
        if loaded.ckpt.get("optimizer") is not None or loaded.ckpt.get("ema") is not None or loaded.ckpt.get("epoch") != -1: fail("CHECKPOINT_NOT_FINALIZED")
        finite_state(loaded.model)
        if fingerprint(path) != before: fail("OUTPUT_CHANGED")
        output.append(path)
    if fatal: fail("TRAINING_POLICY_FAILED")
    return output, {"effective": effective, "versions": {"torch": torch.__version__, "torchvision": torchvision.__version__, "ultralytics": version},
        "optimizer_steps": len(steps), "completed_epochs": len(epochs), "safe_load_count": len(loads), "threads": 2, "device": "cpu"}
