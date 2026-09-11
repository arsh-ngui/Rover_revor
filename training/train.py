"""
train.py — Stage 1: fine-tune a YOLOv8 detector to find "person" in thermal images.

WHAT THIS DOES
    Loads a COCO-pretrained YOLOv8 checkpoint (already knows general shapes/edges
    from millions of RGB photos) and fine-tunes it on your thermal "person" dataset.
    We use transfer learning rather than training from scratch because thermal
    person-detection datasets (thousands of images) are far too small to train a
    detector's backbone from random weights — see README.md section "Transfer
    learning & thermal images" for the full reasoning.

RUN
    python scripts/train.py --data data/dataset.yaml --epochs 60 --imgsz 640 --batch 16

    (On CPU-only machines, drop --batch to 4-8 and expect training to be slow —
    strongly prefer Google Colab's free T4 GPU for Stage 1; see README.md.)

OUTPUT
    Ultralytics writes everything to outputs/runs/detect/<name>/, including:
        weights/best.pt       <- the checkpoint with the best validation mAP (USE THIS ONE)
        weights/last.pt       <- checkpoint from the final epoch
        results.png, results.csv, confusion_matrix.png, PR_curve.png, val_batch*.jpg

IF IT FAILS
    - "CUDA out of memory"        -> lower --batch (try 8, then 4) or lower --imgsz to 512
    - "FileNotFoundError: dataset.yaml path"  -> the `path:` field in data/dataset.yaml
      must be an ABSOLUTE path that actually exists on disk
    - Training runs but mAP stays near 0 after 10+ epochs -> check labels: run
      `python src/preprocessing/prepare_dataset.py --selftest` to confirm the
      pipeline works, then visually inspect a few outputs/runs/.../train_batch*.jpg
      images (Ultralytics saves these automatically) to confirm boxes align with people.
"""

import argparse
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    # ── Data / model ────────────────────────────────────────────────────
    parser.add_argument("--data", type=str, default="data/dataset.yaml",
                         help="Path to dataset.yaml")
    parser.add_argument("--weights", type=str, default="yolov8n.pt",
                         help="Starting checkpoint. yolov8n.pt (nano, ~3.2M params) is the right "
                              "default for a first prototype: fastest to train, smallest, still "
                              "usually good enough to prove the concept. Switch to yolov8s.pt once "
                              "Stage 1 works and you want more accuracy (see README.md model-size table).")

    # ── Core hyperparameters (sensible defaults for a student project) ──
    parser.add_argument("--epochs", type=int, default=60,
                         help="60 is a reasonable starting point for a few-thousand-image dataset. "
                              "Watch results.png: if val loss is still dropping at epoch 60, increase "
                              "this; if it plateaus/rises (overfitting) by epoch 30-40, lower it or "
                              "rely on --patience early stopping instead of guessing.")
    parser.add_argument("--imgsz", type=int, default=640,
                         help="640 matches how most thermal datasets (FLIR, LLVIP, Roboflow) are sized "
                              "and matches the pretrained weights' training resolution. Keep it unless "
                              "you have a specific reason (e.g. very small/far-away people -> try 960, "
                              "at the cost of speed and VRAM).")
    parser.add_argument("--batch", type=int, default=16,
                         help="16 fits comfortably on an 8GB GPU (incl. free Colab T4) at imgsz=640 "
                              "for yolov8n/s. Halve it if you hit CUDA OOM; you can raise it on bigger "
                              "GPUs to speed up training.")
    parser.add_argument("--lr0", type=float, default=0.01,
                         help="Initial learning rate. Ultralytics' default (0.01 with SGD, or 0.001-0.01 "
                              "with Adam-family optimizers) works well out of the box for fine-tuning — "
                              "don't tune this until everything else works.")
    parser.add_argument("--optimizer", type=str, default="auto",
                         help="'auto' lets Ultralytics pick (usually SGD for detection). Fine to leave alone.")
    parser.add_argument("--patience", type=int, default=15,
                         help="Early stopping: stop if val mAP doesn't improve for this many epochs. "
                              "Prevents wasting time/overfitting once the model has converged.")

    # ── Transfer learning controls ───────────────────────────────────────
    parser.add_argument("--freeze", type=int, default=0,
                         help="Number of leading backbone layers to freeze (weights not updated). "
                              "0 = fine-tune the whole network (recommended default: thermal images "
                              "differ enough from RGB that letting early layers adapt helps). Try "
                              "--freeze 10 only if you have a VERY small dataset (<300 images) and see "
                              "overfitting, since freezing early layers keeps generic edge/texture "
                              "filters intact and only adapts the head.")

    # ── Augmentation (defaults tuned down slightly for thermal) ─────────
    parser.add_argument("--hsv_h", type=float, default=0.0,
                         help="Hue augmentation. Set to 0 for thermal: hue is meaningless on a "
                              "single-channel/false-colour thermal image and can teach the model "
                              "to rely on color artifacts that don't generalize across cameras.")
    parser.add_argument("--hsv_s", type=float, default=0.0,
                         help="Saturation augmentation. Same reasoning as hsv_h — disable for thermal.")
    parser.add_argument("--hsv_v", type=float, default=0.3,
                         help="Brightness/value augmentation. KEEP this one fairly active for thermal: "
                              "it simulates the intensity shifts you get between different thermal "
                              "cameras, ambient temperatures, and time of day, which is exactly the "
                              "kind of robustness you want (see README.md 'avoiding camera-specific "
                              "artifacts').")
    parser.add_argument("--fliplr", type=float, default=0.5, help="Horizontal flip probability.")
    parser.add_argument("--mosaic", type=float, default=1.0,
                         help="Mosaic augmentation (combines 4 images). Helps a lot with small datasets; "
                              "Ultralytics automatically disables it for the last ~10 epochs.")

    # ── Bookkeeping ───────────────────────────────────────────────────────
    parser.add_argument("--project", type=str, default="outputs/runs/detect")
    parser.add_argument("--name", type=str, default="stage1_person_detector")
    parser.add_argument("--device", type=str, default="",
                         help="'' = auto-detect (GPU if available, else CPU). Force with '0' (first GPU) or 'cpu'.")
    parser.add_argument("--workers", type=int, default=4, help="Dataloader worker processes.")

    args = parser.parse_args()

    data_yaml = Path(args.data)
    if not data_yaml.exists():
        raise FileNotFoundError(
            f"{data_yaml} not found. Did you run src/preprocessing/prepare_dataset.py "
            f"or scripts/download_dataset.py first, and update data/dataset.yaml's `path:`?"
        )

    print(f"Loading pretrained checkpoint: {args.weights}")
    model = YOLO(args.weights)

    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        lr0=args.lr0,
        optimizer=args.optimizer,
        patience=args.patience,
        freeze=args.freeze if args.freeze > 0 else None,
        hsv_h=args.hsv_h,
        hsv_s=args.hsv_s,
        hsv_v=args.hsv_v,
        fliplr=args.fliplr,
        mosaic=args.mosaic,
        project=args.project,
        name=args.name,
        device=args.device,
        workers=args.workers,
        # save a checkpoint every 10 epochs in addition to best/last, in case
        # training gets interrupted (Colab disconnects, laptop sleeps, etc.)
        save_period=10,
        exist_ok=True,
        plots=True,
    )

    best_path = Path(args.project) / args.name / "weights" / "best.pt"
    print(f"\nTraining complete. Best checkpoint: {best_path}")
    print(f"Next: python scripts/validate.py --weights {best_path}")


if __name__ == "__main__":
    main()
