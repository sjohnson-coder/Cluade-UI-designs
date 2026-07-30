# GodMode Gold Bot V14.1.22 MT5 Runtime Fix

## Confirmed failure

The Windows backend could start while the MetaTrader5 Python module failed to import with:

`AttributeError: _ARRAY_API not found`

The packaged `MetaTrader5==5.0.45` binary uses the NumPy 1.x C API, while the unpinned installation could receive NumPy 2.x through matplotlib. The bridge caught the import exception and continued with `mt5 = None`, leaving the dashboard online but MT5 permanently unavailable.

## Corrections

- Pins Windows NumPy to `1.26.4` before installing MetaTrader5.
- Verifies NumPy and MetaTrader5 binary compatibility on every startup.
- Automatically removes and reinstalls incompatible NumPy/MetaTrader5 packages.
- Adds `FIX_MT5_RUNTIME.bat` for existing installations.
- Adds `VERIFY_MT5_RUNTIME.py` for import and broker-connection diagnostics.
- Routes restored backend launchers through the verified virtual environment.
- Preserves the V14.1.21 settings-origin fix, sans-serif UI, Tick Guard files and full operational package.

## Safe startup state

Live Trading and Auto Trading remain OFF, Dry Run remains ON, and live certification remains required in the packaged defaults.
