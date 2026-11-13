"""Walk-forward 研究框架（階段三的前置工作）。

python -m papertrade.research fetch   [--out research/data] [--skip-chips] [--chips-from YYYY-MM-DD] [--write-holdout]
python -m papertrade.research run     --variant baseline [--variant ...] [--out research/results]
python -m papertrade.research compare --base baseline --variant X
python -m papertrade.research request research/requests/xxx.json      （GitHub Actions 用）

說明見 research/README.md。保留段（最後 20%）未經 Brad 本人同意不得使用。
"""
from .dataset import (HOLDOUT_ENV, HOLDOUT_KEY, HoldoutLocked, boundary, fetch, fetch_chips, fetch_fundamentals,  # noqa: F401
                      fetch_prices, finalize, leaks, load_dataset, manifest_hash, merge_dataset, read_manifest,
                      split_dataset)
from .report import REGISTERED_TRIALS, compare, log_trial, n_trials, read_trials, var_trials  # noqa: F401
from .request import BadRequest, load_request, validate  # noqa: F401
from .runner import (FOLDS, LOOKBACK, METHOD_IDS, VARIANTS, evaluate, folds, patched_config, run_variant, simulate,  # noqa: F401
                     variant_hash, window_px)
