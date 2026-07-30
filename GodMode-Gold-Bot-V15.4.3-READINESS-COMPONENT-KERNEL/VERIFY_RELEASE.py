from __future__ import annotations
from pathlib import Path, PurePosixPath
import hashlib, zipfile, sys, tempfile, shutil, json, stat, ast

ROOT = Path(__file__).resolve().parent

def _read_build_identity() -> tuple[str, str]:
    """V14.1.18: read build identity from backend/app.py so a release rename never
    diverges from the enforced build string. Ends the class of bugs where the signer
    said V14.1.15 while the runtime said V14.1.16 — no cert could pass the exact-build gate."""
    app_py = ROOT / 'backend' / 'app.py'
    build = None
    version = None
    for line in app_py.read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if s.startswith('BUILD_ID') and build is None:
            _, _, rhs = s.partition('=')
            build = rhs.strip().strip('"').strip("'")
        elif s.startswith('APP_VERSION') and version is None:
            _, _, rhs = s.partition('=')
            version = rhs.strip().strip('"').strip("'")
        if build and version:
            break
    if not build or not version:
        raise RuntimeError('BUILD_ID or APP_VERSION missing in backend/app.py')
    return build, version

EXPECTED_BUILD, EXPECTED_VERSION = _read_build_identity()
EXPECTED_CSS = 'aeafedccd428501f1d36853743327bf6c4eced74eb95b2b9c128dc4fb831a69c'
FORBIDDEN_NAMES = {'__pycache__','.pytest_cache','node_modules','.pnpm-store','.DS_Store','settings_save_audit.jsonl','godmode.log'}
FORBIDDEN_SUFFIXES = {'.pyc','.sqlite','.sqlite3','.db','.log'}
MAX_ARCHIVE_MEMBERS = 20_000
MAX_ARCHIVE_FILE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 2_000

def is_release_file(path: Path, root: Path) -> bool:
    rel=path.relative_to(root)
    if any(part in FORBIDDEN_NAMES for part in rel.parts):
        return False
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return False
    if rel.parts and rel.parts[0]=='data':
        return False
    if len(rel.parts)>=2 and rel.parts[:2]==('backend','data'):
        return path.name in {'settings.json','.gitkeep'}
    return True

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def verify_tree(root: Path, pristine: bool=False) -> list[str]:
    errors=[]
    required=[
        root/'backend/app.py',
        root/'frontend/src/lib/api.ts',
        root/'mt5_ea/GodModeTickGuard.mq5',
        root/'backend/services/live_certification.py',
        root/'backend/services/exit_policy_replay.py',
        root/'backend/services/protection_determinism.py',
        root/'backend/services/missed_move_replay.py',
        root/'backend/services/mt5_bridge.py',
        root/'SIGN_LIVE_CERTIFICATION.py',
        root/'RELEASE_MANIFEST.json',
        root/'GODMODE_SETTINGS_V14_1_23.json',
        root/'START_GODMODE.bat',
        root/'start_all.bat',
        root/'COMPILE_TICK_GUARD_V15_1_0.bat',
        root/'COMPILE_TICK_GUARD_V14_1_18.bat',
        root/'live_certification.template.json',
        root/'V15_1_0_RELEASE_NOTES.md',
        root/'V15_1_0_VERIFICATION_REPORT.md',
        root/'CHECK_TICK_GUARD.bat',
        root/'VERIFY_TICK_GUARD.py',
        root/'V14_1_18_RELEASE_NOTES.md',
        root/'V14_1_18_VERIFICATION_REPORT.md',
        root/'V14_1_15_SECURITY_AND_RELIABILITY.md',
    ]
    for p in required:
        if not p.is_file(): errors.append(f'missing required file: {p.relative_to(root)}')
    if errors: return errors
    app=(root/'backend/app.py').read_text(encoding='utf-8')
    app_tree=ast.parse(app)
    def function_source(name: str) -> str:
        node=next((n for n in app_tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name),None)
        if node is None:
            return ''
        return '\n'.join(app.splitlines()[node.lineno-1:node.end_lineno])
    fe=(root/'frontend/src/lib/api.ts').read_text(encoding='utf-8')
    ea=(root/'mt5_ea/GodModeTickGuard.mq5').read_text(encoding='utf-8')
    launcher=(root/'START_GODMODE.bat').read_text(encoding='utf-8')
    deployed_html=(root/'frontend/dist/index.html').read_text(encoding='utf-8')
    expected_cache='V1543-READINESS-COMPONENT-KERNEL'
    launcher_requirements=(
        f'set "GODMODE_BUILD={EXPECTED_BUILD}"',
        f'title GodMode Gold Bot V{EXPECTED_VERSION}',
        f'DASHBOARD_URL=http://127.0.0.1:8000/?build={expected_cache}',
        f'V{EXPECTED_VERSION} did not become ready',
    )
    for token in launcher_requirements:
        if token not in launcher:
            errors.append(f'active launcher identity mismatch: {token}')
    if any(stale in launcher for stale in ('V14.1.23','V15.0.0','V15.0.3','V15.0.5','V15.0.6')):
        errors.append('active launcher contains stale release identity')
    if f'<meta name="godmode-build" content="{EXPECTED_BUILD}"' not in deployed_html:
        errors.append('deployed HTML godmode-build identity mismatch')
    if any(stale in deployed_html for stale in ('V14.1.23','V15.0.0','V15.0.3','V15.0.5','V15.0.6')):
        errors.append('deployed HTML contains stale release identity')
    assets=root/'frontend/dist/assets'
    js_files=sorted(assets.glob('*.js'))
    js=''.join(p.read_text(encoding='utf-8', errors='ignore') for p in js_files)
    for name,text in [('backend',app),('frontend source',fe),('frontend bundle',js),('Tick Guard source',ea)]:
        if EXPECTED_BUILD not in text: errors.append(f'{name}: build identity mismatch')
    expected_main='index-V1543-READINESS-COMPONENT-KERNEL.js'
    expected_settings='Settings-V1513-JOURNAL-DRIVEN-FIXES.js'
    expected_css='index-V1543-READINESS-COMPONENT-KERNEL.css'
    for asset in (expected_main, expected_settings, expected_css):
        if not (assets/asset).is_file(): errors.append(f'missing deployed asset: frontend/dist/assets/{asset}')
    if f'/assets/{expected_main}' not in deployed_html or f'/assets/{expected_css}' not in deployed_html:
        errors.append('deployed HTML does not reference the packaged assets')
    if any(stale in js for stale in ('V14.1.22','V14.1.23','V15.0.0','V15.0.3-PRE-LIVE-SAFETY-HARDENED','V15.0.5-OPERATIONAL-CONTROLS-FIX','V15.0.6-TELEGRAM-CONTROLS-HARDENED')):
        errors.append('deployed JavaScript contains stale active release controls')
    settings_source=(root/'frontend/src/pages/Settings.tsx').read_text(encoding='utf-8')
    theme_source=(root/'frontend/src/styles/theme.css').read_text(encoding='utf-8')
    frontend_html=(root/'frontend/index.html').read_text(encoding='utf-8')
    required_frontend_tokens=(
        (fe, '/api/settings/validation-lock', 'frontend validation-lock API missing'),
        (fe, 'refreshExecutionReadiness', 'frontend authoritative readiness refresh missing'),
        (settings_source, 'const validationToggle=async', 'immediate validation toggle missing'),
        (frontend_html, 'family=Archivo', 'Archivo font import missing'),
        (theme_source, 'Archivo', 'Archivo theme typography missing'),
        (js, '/api/settings/validation-lock', 'deployed validation-lock control missing'),
    )
    for source,token,message in required_frontend_tokens:
        if token not in source: errors.append(message)
    if list((root/'frontend').rglob('*.woff')) or list((root/'frontend').rglob('*.woff2')):
        errors.append('font binary files must not be included in the release')
    telegram_tokens=('_telegram_api_result', 'parse entities', '/api/telegram/recap')
    for token in telegram_tokens:
        if token not in app: errors.append(f'Telegram operational fix missing: {token}')

    protection_source=(root/'backend/services/protection_determinism.py').read_text(encoding='utf-8')
    replay_source=(root/'backend/services/missed_move_replay.py').read_text(encoding='utf-8')
    bridge_source=(root/'backend/services/mt5_bridge.py').read_text(encoding='utf-8')
    manager=function_source('_auto_manage_open_trades')
    burst=function_source('_maybe_execute_protected_burst_add')
    staged=function_source('_maybe_execute_staged_pyramid_add')
    loss_governor=function_source('_loss_feedback_governor')
    auto_tick=function_source('_auto_trade_tick')
    missed_route=function_source('journal_missed_pumps')
    ai_monitor=function_source('ai_monitor_status')
    determinism_requirements=(
        (protection_source,'broker_profit_stop_confirmed','broker-confirmed profitable-stop gate missing'),
        (protection_source,'elapsed_confirmation','elapsed-time confirmation helper missing'),
        (protection_source,'broker_open_epoch','broker-open timestamp reconstruction missing'),
        (protection_source,'valid_live_atr','fail-closed live ATR helper missing'),
        (manager,'v14_activation = threshold_activated','V14 protection threshold gate missing'),
        (manager,'broker_profit_stop_confirmed(direction, entry, sl, current_price)','BREATH broker confirmation gate missing'),
        (manager,'_persist_protection_event("peak"','immediate peak persistence missing'),
        (manager,'_persist_protection_event("broker_sl_confirmed"','broker-confirmed SL persistence missing'),
        (manager,'broker_open_epoch(pos)','broker-derived trade age missing'),
        (manager,'dynamicSlCooldownSeconds','elapsed-seconds cooldown missing'),
        (manager,'command = "BREATH" if give_room else "PROTECT"','authoritative protection directives missing'),
        (replay_source,'deduplicate_events','missed-event deduplication missing'),
        (replay_source,'bestExitPrice','executable replay exit-price evidence missing'),
        (bridge_source,'def copy_ticks_range','MT5 chronological tick-range bridge missing'),
        (bridge_source,'"openTimeMsc"','MT5 position millisecond open timestamp missing'),
        (missed_route,'mt5_bridge.order_calc_profit','broker-native missed-move P/L missing'),
        (missed_route,'replay_executable_ticks','chronological executable replay missing'),
        (burst,'valid_live_atr(market)','Protected Burst live-ATR gate missing'),
        (staged,'valid_live_atr(market)','pyramiding live-ATR gate missing'),
        (loss_governor,'valid_live_atr(market)','post-loss re-entry live-ATR gate missing'),
        (auto_tick,'Repeat-setup guard blocked: valid live ATR unavailable','repeat-entry live-ATR gate missing'),
        (ai_monitor,'"reason": "live_atr_unavailable"','AI monitor live-ATR truth response missing'),
    )
    for source,token,message in determinism_requirements:
        if token not in source: errors.append(message)
    for legacy in ('dynamicSlRecoverConfirmations','dynamicSlCutConfirmations','dynamicSlCooldownChecks','dynamicSlGraceChecks','dynamicSlMaxHoldChecks'):
        if legacy in manager: errors.append(f'protection manager still uses loop-count timer: {legacy}')
    if '_execute_mt5_mutation_serialized("MODIFY_SL"' in manager or "_execute_mt5_mutation_serialized('MODIFY_SL'" in manager:
        errors.append('Python protection manager still mutates broker SL directly')
    for source,name in ((burst,'Protected Burst'),(staged,'staged pyramiding'),(loss_governor,'loss-feedback governor'),(auto_tick,'auto-entry repeat guard'),(ai_monitor,'AI monitor')):
        if 'market.get("atr14") or 8' in source or 'market.get("atr14") or market.get("atr") or 8.0' in source:
            errors.append(f'{name} still substitutes synthetic ATR 8.0')
    if app.count('@app.get("/api/journal/missed-pumps")') != 1:
        errors.append('missed-move route is registered more than once')
    ea_requirements=('freshOwner','"PROTECT"','"RECOVER"','"BREATH"','brokerConfirmedProfit','profitAtr>=g_ctrlProtectStartAtr','policyAtr>0')
    for token in ea_requirements:
        if token not in ea: errors.append(f'Tick Guard deterministic actuator token missing: {token}')
    if 'if(!freshOwner' not in ea:
        errors.append('Tick Guard fallback can compete with a fresh Python stop policy')
    dashboard_source=(root/'frontend/src/pages/Dashboard.tsx').read_text(encoding='utf-8')
    if 'chronological broker bid/ask ticks' not in dashboard_source or 'real M5 candles after the miss' in dashboard_source:
        errors.append('missed-move dashboard copy does not describe executable tick replay')

    manifest=json.loads((root/'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))
    if manifest.get('version') != EXPECTED_VERSION or manifest.get('buildId') != EXPECTED_BUILD:
        errors.append('manifest identity mismatch')
    tick_guard = manifest.get('tickGuard')
    if not isinstance(tick_guard, dict):
        errors.append('manifest does not disclose Tick Guard source-only status')
    else:
        if tick_guard.get('sourceIncluded') is not True:
            errors.append('manifest does not confirm Tick Guard source inclusion')
        if tick_guard.get('compiledEx5Included') is not False:
            errors.append('manifest incorrectly claims compiled Tick Guard inclusion')
        if not str(tick_guard.get('protectionStatus') or '').startswith('INCOMPLETE'):
            errors.append('manifest does not disclose incomplete Tick Guard live protection')
    manifest_rows=manifest.get('files') or []
    manifest_map={}
    for row in manifest_rows:
        if not isinstance(row,dict) or not isinstance(row.get('path'),str):
            errors.append('manifest contains malformed file row')
            continue
        rel=row['path']
        if rel in manifest_map:
            errors.append(f'manifest duplicate file: {rel}')
            continue
        manifest_map[rel]=row
        file_path=root/rel
        if not file_path.is_file():
            errors.append(f'manifest unexpected file: {rel}')
            continue
        if row.get('sha256') != sha256(file_path) or int(row.get('size',-1)) != file_path.stat().st_size:
            errors.append(f'manifest file checksum mismatch: {rel}')
    expected_manifest={
        file_path.relative_to(root).as_posix()
        for file_path in root.rglob('*')
        if file_path.is_file()
        and file_path.name not in {'RELEASE_MANIFEST.json','SHA256SUMS.txt'}
        and is_release_file(file_path,root)
    }
    for rel in sorted(expected_manifest-set(manifest_map)):
        errors.append(f'manifest missing file: {rel}')
    for rel in sorted(set(manifest_map)-expected_manifest):
        errors.append(f'manifest unexpected file: {rel}')
    settings=json.loads((root/'GODMODE_SETTINGS_V14_1_23.json').read_text(encoding='utf-8'))
    allowed_roots_node=next((
        n for n in app_tree.body
        if isinstance(n,(ast.Assign,ast.AnnAssign))
        and any(isinstance(t,ast.Name) and t.id=='_SETTINGS_ALLOWED_ROOTS' for t in (n.targets if isinstance(n,ast.Assign) else [n.target]))
    ),None)
    try:
        allowed_roots=set(ast.literal_eval(allowed_roots_node.value)) if allowed_roots_node is not None else set()
    except Exception:
        allowed_roots=set()
    if not allowed_roots:
        errors.append('unable to verify packaged settings root schema')
    else:
        unknown_roots=sorted(set(settings)-allowed_roots)
        if unknown_roots:
            errors.append('packaged settings contain unknown section(s): '+', '.join(unknown_roots))
    if settings.get('appVersion') != EXPECTED_VERSION or settings.get('buildId') != EXPECTED_BUILD:
        errors.append('packaged settings identity mismatch')
    if not bool((settings.get('execution') or {}).get('requireLiveCertification')):
        errors.append('packaged settings do not fail closed on live certification')
    execution=settings.get('execution') or {}
    if execution.get('liveCertificationMode') != 'local_runtime':
        errors.append('packaged settings do not select local runtime attestation')
    if bool(execution.get('liveTradingEnabled')) or bool(execution.get('autoTradingEnabled')) or not bool(execution.get('dryRun')):
        errors.append('packaged settings are not safely disarmed')
    prelive=execution.get('preLiveSafety') or {}
    if execution.get('deploymentMode') != 'LIVE_RESTRICTED' or prelive.get('mode') != 'LIVE_RESTRICTED':
        errors.append('packaged settings do not default to LIVE_RESTRICTED')
    if bool(prelive.get('allowComplexEntries')) or float(prelive.get('maxRestrictedVolume', 0)) > 0.01 or int(prelive.get('maxOpenPositions', 0)) != 1:
        errors.append('packaged restricted-live limits are unsafe')
    if not (root/'backend/services/prelive_safety.py').is_file():
        errors.append('pre-live safety supervisor missing')
    backend_settings=json.loads((root/'backend/data/settings.json').read_text(encoding='utf-8'))
    if backend_settings != settings:
        errors.append('root and backend packaged settings differ')
    automation=settings.get('automation') or {}
    if not bool(automation.get('requireTickGuardForLive')):
        errors.append('packaged settings do not require the authoritative Tick Guard')
    for key in ('dynamicSlCooldownSeconds','dynamicSlRecoverConfirmSeconds','dynamicSlCutConfirmSeconds','dynamicSlGraceSeconds','dynamicSlMaxHoldSeconds','dynamicSlDecisionMaxAgeSeconds'):
        if float(automation.get(key,0) or 0) <= 0:
            errors.append(f'packaged elapsed-time protection setting missing: {key}')
    for legacy in ('dynamicSlCooldownChecks','dynamicSlGraceChecks','dynamicSlMaxHoldChecks','dynamicSlRecoverConfirmations','dynamicSlCutConfirmations'):
        if legacy in automation:
            errors.append(f'packaged legacy loop-count setting remains: {legacy}')
    trade_management=(settings.get('trading') or {}).get('tradeManagement') or {}
    if float(trade_management.get('profitLockFraction', -1)) != 0.62:
        errors.append('packaged legacy profit-lock default differs from audited 0.62')
    if float(trade_management.get('aiDynamicMaxGivebackFraction', -1)) != 0.45:
        errors.append('packaged dynamic-SL giveback default differs from audited 0.45')
    if '#property version   "15.043"' not in ea:
        errors.append('Tick Guard source property version mismatch')
    if 'TimeCurrent()' in ea or 'TimeGMT()' not in ea:
        errors.append('Tick Guard does not use UTC freshness semantics')
    requirements=(root/'backend/requirements.txt').read_text(encoding='utf-8')
    if 'numpy==1.26.4' not in requirements or 'MetaTrader5==5.0.45' not in requirements:
        errors.append('MT5 binary compatibility pins are missing')
    certificate=json.loads((root/'live_certification.template.json').read_text(encoding='utf-8'))
    if certificate.get('buildId') != EXPECTED_BUILD:
        errors.append('live certification template identity mismatch')
    if certificate.get('schemaVersion') != 2:
        errors.append('live certification template schema is not signed-evidence V2')
    if certificate.get('signatureAlgorithm') != 'hmac-sha256':
        errors.append('live certification template signature algorithm mismatch')
    if certificate.get('signature'):
        errors.append('live certification template must not ship pre-signed')
    if any(bool(row.get('passed')) for row in (certificate.get('gates') or {}).values() if isinstance(row,dict)):
        errors.append('live certification template contains pre-approved evidence')
    if any(bool(row.get('sha256')) for row in (certificate.get('gates') or {}).values() if isinstance(row,dict)):
        errors.append('live certification template contains pre-hashed evidence')
    active_installers=(
        'README.md','START_INSTRUCTIONS.txt','start_all.bat','start_backend.bat',
        'start_backend_mobile.bat','CHECK_TICK_GUARD.bat',
        '2_INSTALL_EA_AND_START_GODMODE.bat','mt5_ea/README_EA_INSTALL.md',
    )
    for relative in active_installers:
        active=(root/relative).read_text(encoding='utf-8')
        if f'V{EXPECTED_VERSION}' not in active:
            errors.append(f'active installer does not identify V{EXPECTED_VERSION}: {relative}')
        if any(stale in active for stale in ('V14.1.23','V15.0.3','V15.0.5','V15.0.6')):
            errors.append(f'active installer contains stale identity: {relative}')
    css_files=list((root/'frontend/dist/assets').glob('*.css'))
    if len(css_files)!=1 or sha256(css_files[0])!=EXPECTED_CSS: errors.append('UI theme CSS hash mismatch')
    if pristine:
        for p in root.rglob('*'):
            if p.is_file() and not is_release_file(p,root):
                errors.append(f'forbidden release artifact: {p.relative_to(root)}')
    sums=root/'SHA256SUMS.txt'
    if not sums.exists(): errors.append('SHA256SUMS.txt missing')
    else:
        listed=set()
        for number,line in enumerate(sums.read_text(encoding='utf-8').splitlines(), start=1):
            if not line.strip(): continue
            try:
                digest,rel=line.split('  ',1)
            except ValueError:
                errors.append(f'malformed checksum line {number}')
                continue
            rel=rel[2:] if rel.startswith('./') else rel
            if rel in listed:
                errors.append(f'duplicate checksum entry: {rel}')
                continue
            listed.add(rel)
            p=root/rel
            if not p.is_file() or sha256(p)!=digest: errors.append(f'checksum mismatch: {rel}')
        expected={
            p.relative_to(root).as_posix()
            for p in root.rglob('*')
            if p.is_file() and p != sums and is_release_file(p,root)
        }
        for rel in sorted(expected-listed): errors.append(f'missing checksum entry: {rel}')
        for rel in sorted(listed-expected): errors.append(f'unexpected checksum entry: {rel}')
    return errors

def safe_extract(archive: Path, destination: Path) -> list[str]:
    errors=[]
    base=destination.resolve()
    normalized_members: dict[str, zipfile.ZipInfo] = {}
    with zipfile.ZipFile(archive) as z:
        members=z.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            errors.append(f'archive has too many members: {len(members)}')
        total_uncompressed=0
        for info in members:
            portable_name=info.filename.replace('\\','/')
            pure=PurePosixPath(portable_name)
            parts=pure.parts
            unsafe=(
                not portable_name
                or pure.is_absolute()
                or any(part in {'', '.', '..'} for part in parts)
                or bool(parts and ':' in parts[0])
            )
            normalized='/'.join(parts)
            if unsafe:
                errors.append(f'unsafe archive path: {info.filename}')
                continue
            if normalized in normalized_members:
                errors.append(f'duplicate archive member: {normalized}')
                continue
            normalized_members[normalized]=info
            target=(destination/Path(*parts)).resolve()
            try:
                target.relative_to(base)
            except ValueError:
                errors.append(f'unsafe archive path: {info.filename}')
            mode=(info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                errors.append(f'archive symlink is not allowed: {info.filename}')
            elif mode not in {0, stat.S_IFREG, stat.S_IFDIR}:
                errors.append(f'archive special file is not allowed: {info.filename}')
            if info.flag_bits & 0x1:
                errors.append(f'encrypted archive member is not allowed: {info.filename}')
            if info.file_size > MAX_ARCHIVE_FILE_BYTES:
                errors.append(f'archive member is too large: {info.filename}')
            total_uncompressed += int(info.file_size)
            if (
                info.file_size > 1_000_000
                and info.compress_size > 0
                and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                errors.append(f'suspicious compression ratio: {info.filename}')
        if total_uncompressed > MAX_ARCHIVE_TOTAL_BYTES:
            errors.append(f'archive expands beyond {MAX_ARCHIVE_TOTAL_BYTES} bytes')
        if errors:
            return errors
        destination.mkdir(parents=True, exist_ok=True)
        for normalized,info in normalized_members.items():
            target=destination/Path(*PurePosixPath(normalized).parts)
            if info.is_dir():
                target.mkdir(parents=True,exist_ok=True)
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info,'r') as source,target.open('xb') as output:
                shutil.copyfileobj(source,output,length=1024*1024)
            permissions=(info.external_attr >> 16) & 0o777
            if permissions:
                target.chmod(permissions)
    return errors

def main() -> int:
    target=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT
    temp=None
    try:
        if target.suffix.lower()=='.zip':
            temp=Path(tempfile.mkdtemp(prefix='godmode_verify_'))
            extraction_errors=safe_extract(target,temp)
            if extraction_errors:
                print('\n'.join('FAIL: '+x for x in extraction_errors)); return 1
            children=[p for p in temp.iterdir() if p.is_dir()]
            root=children[0] if len(children)==1 else temp
            errors=verify_tree(root, pristine=True); mode='archive'
        else:
            errors=verify_tree(target, pristine=False); mode='runtime installation'
        if errors:
            print('\n'.join('FAIL: '+x for x in errors)); return 1
        print(f'PASS: V{EXPECTED_VERSION} {mode} identity, UI hash and checksums verified.')
        return 0
    finally:
        if temp: shutil.rmtree(temp,ignore_errors=True)
if __name__=='__main__': raise SystemExit(main())
