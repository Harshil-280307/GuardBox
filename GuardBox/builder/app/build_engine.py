"""
TRINETRA Builder - Core Build Engine (Phase 6.4)
Handles isolated workspace lifecycle, Windows package assembly, Android APK compilation,
Inno Setup customer installer compilation, critical security scanning, Build-Info.txt generation,
and post-build cleanup.
"""

import os
import sys
import re
import json
import shutil
import zipfile
import subprocess
import datetime
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .schemas import CustomerBuildConfig, BuildExecutionResult
from .validator import validate_customer_config, sanitize_folder_name


BUILDER_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BUILDER_ROOT.parent
WORKSPACE_BASE = BUILDER_ROOT / "workspace"
BUILDS_OUTPUT_BASE = PROJECT_ROOT / "TRINETRA-BUILDS"


class BuildEngine:
    def __init__(self, config: CustomerBuildConfig):
        self.config = config
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.build_id = f"BUILD-{self.timestamp}-{uuid.uuid4().hex[:6].upper()}"
        self.workspace_dir = WORKSPACE_BASE / self.build_id
        self.sanitized_shop_name = sanitize_folder_name(config.shop_name) if config else "TRINETRA-CUSTOMER"
        self.output_dir = BUILDS_OUTPUT_BASE / self.sanitized_shop_name
        self.logs: List[str] = []
        self.errors: List[str] = []
        self.artifacts: List[str] = []

    def log(self, message: str, stage: Optional[str] = None):
        prefix = f"[{stage}] " if stage else ""
        formatted = f"{prefix}{message}"
        self.logs.append(formatted)

    @staticmethod
    def check_inno_setup() -> Optional[str]:
        """
        Locates the Inno Setup compiler (ISCC.exe) using:
        1. Configured environment variable (ISCC_PATH or INNO_SETUP_PATH)
        2. Standard Windows installation paths (64-bit and 32-bit Program Files, LocalAppData)
        3. System PATH lookup
        """
        # 1. Environment variable
        env_iscc = os.environ.get("ISCC_PATH") or os.environ.get("INNO_SETUP_PATH")
        if env_iscc and os.path.isfile(env_iscc):
            return env_iscc

        # 2. Standard Windows Installation Paths
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app_data = os.environ.get("LocalAppData", "")

        candidates = [
            os.path.join(program_files_x86, "Inno Setup 6", "ISCC.exe"),
            os.path.join(program_files, "Inno Setup 6", "ISCC.exe"),
            os.path.join(program_files_x86, "Inno Setup 5", "ISCC.exe"),
            os.path.join(program_files, "Inno Setup 5", "ISCC.exe"),
            r"C:\Inno Setup 6\ISCC.exe",
            r"C:\InnoSetup\ISCC.exe",
            r"C:\ProgramData\chocolatey\bin\iscc.exe",
        ]

        if local_app_data:
            candidates.append(os.path.join(local_app_data, "Programs", "Inno Setup 6", "ISCC.exe"))

        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate

        # 3. System PATH lookup
        iscc_path = shutil.which("iscc") or shutil.which("iscc.exe") or shutil.which("ISCC")
        if iscc_path and os.path.isfile(iscc_path):
            return iscc_path

        return None

    def execute_build(self) -> BuildExecutionResult:
        """Executes the full 8-stage customer build and packaging pipeline."""
        windows_status = "SKIPPED"
        android_status = "SKIPPED"
        security_scan_status = "NOT_RUN"
        is_success = True
        installer_available = False

        try:
            # -------------------------------------------------------------
            # Stage 1: Validating configuration
            # -------------------------------------------------------------
            self.log("Starting configuration validation...", "1/8")
            val_result = validate_customer_config(self.config)
            if not val_result.is_valid:
                for err in val_result.errors:
                    self.errors.append(err)
                    self.log(f"Validation Error: {err}", "1/8")
                return BuildExecutionResult(
                    build_id=self.build_id,
                    shop_id=self.config.shop_id,
                    shop_name=self.config.shop_name,
                    is_success=False,
                    windows_status="FAILED",
                    android_status="FAILED",
                    installer_available=False,
                    security_scan_status="FAILED",
                    output_directory=str(self.output_dir),
                    artifacts=[],
                    logs=self.logs,
                    errors=self.errors
                )
            self.log(f"Configuration valid for customer '{self.config.shop_name}' ({self.config.shop_id}).", "1/8")

            # -------------------------------------------------------------
            # Stage 2: Creating temporary workspace
            # -------------------------------------------------------------
            self.log(f"Creating isolated build workspace at {self.workspace_dir}...", "2/8")
            self.workspace_dir.mkdir(parents=True, exist_ok=True)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.log("Workspace initialized.", "2/8")

            # -------------------------------------------------------------
            # Stage 3: Preparing Windows application
            # -------------------------------------------------------------
            win_staged_dir = None
            if self.config.build_windows:
                self.log("Preparing Windows application configuration...", "3/8")
                win_workspace = self.workspace_dir / "windows"
                win_workspace.mkdir(parents=True, exist_ok=True)

                # 1. Generate customer .env
                env_content = (
                    f"# TRINETRA Customer Environment Configuration\n"
                    f"# Shop: {self.config.shop_name} ({self.config.shop_id})\n"
                    f"# Generated at {datetime.datetime.now().isoformat()}\n\n"
                    f"FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json\n"
                    f"FIREBASE_DATABASE_URL={self.config.firebase_db_url.strip()}\n"
                    f"SUPABASE_URL={self.config.supabase_url.strip()}\n"
                    f"SUPABASE_SECRET_KEY={self.config.supabase_secret_key.strip()}\n"
                    f"SUPABASE_BUCKET={self.config.supabase_bucket.strip()}\n"
                    f"GUARDBOX_DEVICE_ID={self.config.device_id.strip()}\n"
                    f"GUARDBOX_SHOP_ID={self.config.shop_id.strip()}\n"
                    f"GUARDBOX_SHOP_NAME={self.config.shop_name.strip()}\n"
                    f"GUARDBOX_DEVICE_NAME={self.config.device_name.strip()}\n"
                    f"VERONIC_ADMIN_USER={self.config.veronic_admin_user.strip()}\n"
                    f"VERONIC_ADMIN_SECRET={self.config.veronic_admin_secret.strip()}\n"
                )
                (win_workspace / ".env").write_text(env_content, encoding="utf-8")

                # 2. Write serviceAccountKey.json
                sa_data = json.loads(self.config.firebase_service_account_json.strip())
                (win_workspace / "serviceAccountKey.json").write_text(json.dumps(sa_data, indent=2), encoding="utf-8")

                # 3. Write data/device_identity.json
                data_dir = win_workspace / "data"
                data_dir.mkdir(parents=True, exist_ok=True)
                (win_workspace / "snapshots").mkdir(parents=True, exist_ok=True)
                
                device_identity_data = {
                    "device_id": self.config.device_id.strip(),
                    "shop_id": self.config.shop_id.strip(),
                    "shop_name": self.config.shop_name.strip(),
                    "device_name": self.config.device_name.strip(),
                    "registered_at": datetime.datetime.now().isoformat(),
                    "is_verified": True
                }
                (data_dir / "device_identity.json").write_text(json.dumps(device_identity_data, indent=2), encoding="utf-8")
                self.log("Customer Windows runtime configuration created in workspace.", "3/8")

                # -------------------------------------------------------------
                # Stage 4: Building desktop launcher + backend package
                # -------------------------------------------------------------
                self.log("Building desktop launcher + backend package...", "4/8")
                dist_src = PROJECT_ROOT / "backend" / "dist" / "TRINETRA"
                if not dist_src.exists() or not (dist_src / "TRINETRA.exe").exists():
                    self.log("Base PyInstaller distribution not found. Building with spec...", "4/8")
                    spec_file = PROJECT_ROOT / "backend" / "trinetra.spec"
                    py_venv = PROJECT_ROOT / "backend" / "venv" / "Scripts" / "pyinstaller.exe"
                    cmd = [str(py_venv) if py_venv.exists() else "pyinstaller", str(spec_file), "--noconfirm"]
                    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT / "backend"), capture_output=True, text=True)
                    if res.returncode != 0:
                        raise RuntimeError(f"PyInstaller build failed: {res.stderr[:300]}")

                # Stage complete application inside workspace/windows/staged_app
                win_staged_dir = win_workspace / "staged_app"
                win_staged_dir.mkdir(parents=True, exist_ok=True)

                for item in dist_src.iterdir():
                    dst = win_staged_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dst)

                # Inject customer runtime files into staged application directory
                shutil.copy2(win_workspace / ".env", win_staged_dir / ".env")
                shutil.copy2(win_workspace / "serviceAccountKey.json", win_staged_dir / "serviceAccountKey.json")
                (win_staged_dir / "data").mkdir(exist_ok=True)
                (win_staged_dir / "snapshots").mkdir(exist_ok=True)
                shutil.copy2(data_dir / "device_identity.json", win_staged_dir / "data" / "device_identity.json")

                windows_status = "SUCCESS"
                self.log("Windows application package assembled successfully.", "4/8")

            # -------------------------------------------------------------
            # Stage 5 & 6: Android Build Pipeline
            # -------------------------------------------------------------
            if self.config.build_android:
                self.log("Preparing Android customer build...", "5/8")
                android_src_dir = PROJECT_ROOT / "android"
                android_workspace = self.workspace_dir / "android"
                
                self.log("Copying isolated Android project template...", "5/8")
                self._copy_android_template(android_src_dir, android_workspace)

                gs_data = json.loads(self.config.google_services_json.strip())
                (android_workspace / "app" / "google-services.json").write_text(json.dumps(gs_data, indent=2), encoding="utf-8")
                self.log("Customer google-services.json placed into Android build workspace.", "5/8")

                self.log("Compiling Android APK with customer build parameters...", "6/8")
                apk_path = self._build_android_apk(android_workspace)
                
                dest_apk_name = f"TRINETRA-{self.sanitized_shop_name}.apk"
                dest_apk_path = self.output_dir / dest_apk_name
                shutil.copy2(apk_path, dest_apk_path)
                
                self.artifacts.append(str(dest_apk_path))
                android_status = "SUCCESS"
                self.log(f"Android APK generated: {dest_apk_name} (debug APK)", "6/8")

            # -------------------------------------------------------------
            # Stage 7: Building Windows installer
            # -------------------------------------------------------------
            if self.config.build_windows and win_staged_dir:
                self.log("Evaluating Inno Setup compiler availability...", "7/8")
                iscc_bin = self.check_inno_setup()

                if iscc_bin:
                    installer_available = True
                    self.log(f"Inno Setup found at '{iscc_bin}'. Generating customer installer...", "7/8")
                    installer_exe = self._compile_inno_setup_installer(iscc_bin, win_staged_dir)
                    self.artifacts.append(str(installer_exe))
                    self.log(f"Installer generated: {installer_exe.name}", "7/8")
                else:
                    installer_available = False
                    self.log("Inno Setup (ISCC.exe) is not installed. Copying standalone application directory to output...", "7/8")
                    customer_pkg_dir = self.output_dir / "Windows" / "TRINETRA"
                    customer_pkg_dir.mkdir(parents=True, exist_ok=True)
                    for item in win_staged_dir.iterdir():
                        dst = customer_pkg_dir / item.name
                        if item.is_dir():
                            shutil.copytree(item, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, dst)
                    self.artifacts.append(str(customer_pkg_dir / "TRINETRA.exe"))

            # -------------------------------------------------------------
            # Stage 8: Validating artifacts, Security scan & cleaning workspace
            # -------------------------------------------------------------
            self.log("Validating generated artifacts and running security scan...", "8/8")
            
            # Security Scan for Android Artifacts
            if self.config.build_android and android_status == "SUCCESS":
                sec_pass, sec_msg = self._perform_android_security_scan(self.output_dir / f"TRINETRA-{self.sanitized_shop_name}.apk")
                if not sec_pass:
                    security_scan_status = "FAILED"
                    self.errors.append(f"Security Alert: {sec_msg}")
                    self.log(f"FAIL — {sec_msg}", "8/8")
                    is_success = False
                else:
                    security_scan_status = "PASSED"
                    self.log("PASS — sensitive server secrets not found in Android artifact.", "8/8")
            else:
                security_scan_status = "PASSED"

            # Generate Build-Info.txt
            self._generate_build_info(windows_status, android_status, installer_available)
            self.artifacts.append(str(self.output_dir / "Build-Info.txt"))
            self.log("Build-Info.txt written to output directory.", "8/8")

            # Workspace Cleanup
            self.log("Cleaning temporary workspace...", "8/8")
            cleanup_ok = self._cleanup_workspace()
            if cleanup_ok:
                self.log("Temporary build workspace cleaned successfully.", "8/8")
            else:
                self.log("Warning: Partial workspace cleanup failure. Check locked file handles.", "8/8")

        except Exception as e:
            is_success = False
            err_str = f"Build failed with exception: {str(e)}"
            self.errors.append(err_str)
            self.log(err_str, "ERROR")

        return BuildExecutionResult(
            build_id=self.build_id,
            shop_id=self.config.shop_id,
            shop_name=self.config.shop_name,
            is_success=is_success and (len(self.errors) == 0),
            windows_status=windows_status,
            android_status=android_status,
            installer_available=installer_available,
            security_scan_status=security_scan_status,
            output_directory=str(self.output_dir),
            artifacts=self.artifacts,
            logs=self.logs,
            errors=self.errors
        )

    def _compile_inno_setup_installer(self, iscc_path: str, staged_app_dir: Path) -> Path:
        """
        Generates customer Inno Setup .iss script and compiles TRINETRA-<Shop>-Setup.exe.
        """
        installer_iss = self.workspace_dir / "trinetra_customer.iss"
        output_base_filename = f"TRINETRA-{self.sanitized_shop_name}-Setup"
        
        # Ensure trinetra.ico is present in workspace for installer icon embedding
        ico_src = PROJECT_ROOT / "installer" / "trinetra.ico"
        if not ico_src.exists():
            ico_src = PROJECT_ROOT / "backend" / "app" / "assets" / "trinetra.ico"
        
        ico_line = ""
        if ico_src.exists():
            shutil.copy2(ico_src, self.workspace_dir / "trinetra.ico")
            ico_line = "SetupIconFile=trinetra.ico\nUninstallIconFile=trinetra.ico"

        iss_content = f"""; ==============================================================================
; TRINETRA Customer Windows Installer (Inno Setup 6 Script)
; Customer: {self.config.shop_name} ({self.config.shop_id})
; Generated at: {datetime.datetime.now().isoformat()}
; ==============================================================================

#define MyAppName "TRINETRA"
#define MyShopName "{self.config.shop_name}"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Veronic"
#define MyAppURL "https://veronic.in"
#define MyAppExeName "TRINETRA.exe"

[Setup]
AppId={{{{E83B5E09-7A8E-4E9A-A37F-{uuid.uuid4().hex[:12].upper()}}}}}
AppName={{#MyAppName}} - {{#MyShopName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
AppUpdatesURL={{#MyAppURL}}
DefaultDirName={{autopf}}\\TRINETRA
DisableProgramGroupPage=yes
OutputBaseFilename={output_base_filename}
{ico_line}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
OutputDir={str(self.output_dir)}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Dirs]
Name: "{{app}}\\data"; Permissions: users-full
Name: "{{app}}\\snapshots"; Permissions: users-full
Name: "{{app}}\\config"; Permissions: users-full

[Files]
; Complete packaged customer application payload
Source: "{str(staged_app_dir)}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{autoprograms}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; IconFilename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon; IconFilename: "{{app}}\\{{#MyAppExeName}}"

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#StringChange(MyAppName, '&', '&&')}}}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Preserve customer sqlite database and snapshots during standard uninstall
; Only remove cache/temp if necessary
"""
        installer_iss.write_text(iss_content, encoding="utf-8")

        # Compile with ISCC
        cmd = [iscc_path, str(installer_iss)]
        res = subprocess.run(cmd, cwd=str(self.workspace_dir), capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Inno Setup compilation failed with exit code {res.returncode}: {res.stderr or res.stdout}")

        generated_installer = self.output_dir / f"{output_base_filename}.exe"
        if not generated_installer.exists():
            raise FileNotFoundError(f"Compiled installer was not found at {generated_installer}")

        return generated_installer

    def _copy_android_template(self, src: Path, dst: Path):
        """Copies Android project structure excluding build artifacts and gradle caches."""
        ignore_patterns = shutil.ignore_patterns(".gradle", ".kotlin", "build", "captures", "*.apk", ".idea")
        shutil.copytree(src, dst, ignore=ignore_patterns)

    def _build_android_apk(self, android_dir: Path) -> Path:
        """Executes Gradle build with customer build parameters."""
        gradlew = android_dir / "gradlew.bat"
        if not gradlew.exists():
            raise FileNotFoundError(f"Gradle wrapper not found at {gradlew}")

        env = os.environ.copy()
        jdk_path = Path(r"C:\Users\Harshil Danidhariya\.jdks\jdk-17.0.12+7")
        if jdk_path.exists():
            env["JAVA_HOME"] = str(jdk_path)
            env["PATH"] = f"{str(jdk_path / 'bin')};{env.get('PATH', '')}"

        cmd = [
            str(gradlew),
            "assembleDebug",
            f"-PcustomDeviceId={self.config.device_id.strip()}",
            f"-PcustomDbUrl={self.config.firebase_db_url.strip()}",
            "--no-daemon"
        ]

        result = subprocess.run(cmd, cwd=str(android_dir), capture_output=True, text=True, env=env)
        if result.returncode != 0:
            error_tail = result.stderr[-500:] if result.stderr else result.stdout[-500:]
            raise RuntimeError(f"Gradle build failed with exit code {result.returncode}: {error_tail}")

        apk_output = android_dir / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        if not apk_output.exists():
            raise FileNotFoundError(f"Generated APK was not found at {apk_output}")

        return apk_output

    def _perform_android_security_scan(self, apk_path: Path) -> Tuple[bool, str]:
        """
        Scans APK contents to guarantee NO sensitive server secrets or private keys were leaked.
        """
        if not apk_path.exists():
            return False, "Android APK artifact missing."

        sensitive_signatures = []
        if self.config.supabase_secret_key:
            sensitive_signatures.append(("Supabase Secret Key", self.config.supabase_secret_key.strip()))
        if self.config.veronic_admin_secret:
            sensitive_signatures.append(("Veronic Admin Secret", self.config.veronic_admin_secret.strip()))

        if self.config.firebase_service_account_json:
            try:
                sa = json.loads(self.config.firebase_service_account_json)
                if "private_key" in sa:
                    sensitive_signatures.append(("Firebase Private Key Header", "-----BEGIN PRIVATE KEY-----"))
                if "client_email" in sa and "@" in sa["client_email"]:
                    sensitive_signatures.append(("Firebase Service Account Email", sa["client_email"]))
            except Exception:
                pass

        try:
            with zipfile.ZipFile(apk_path, "r") as zf:
                for file_info in zf.infolist():
                    content = zf.read(file_info)
                    for name, secret in sensitive_signatures:
                        if not secret or len(secret) < 4:
                            continue
                        if secret.encode("utf-8") in content:
                            return False, f"Sensitive secret '{name}' detected in APK file '{file_info.filename}'!"
        except Exception as e:
            return False, f"Could not analyze APK zip structure: {str(e)}"

        return True, "Security scan passed."

    def _generate_build_info(self, win_status: str, android_status: str, installer_avail: bool):
        """Generates safe customer Build-Info.txt."""
        win_desc = "generated (standalone package)" if win_status == "SUCCESS" else win_status
        if installer_avail and win_status == "SUCCESS":
            win_desc = "generated (Setup.exe installer)"
        android_desc = "generated (debug APK)" if android_status == "SUCCESS" else android_status

        info_lines = [
            "TRINETRA",
            "Customer Build Information",
            "==================================================",
            f"Shop Name: {self.config.shop_name}",
            f"Shop ID: {self.config.shop_id}",
            f"Device ID: {self.config.device_id}",
            f"Device Name: {self.config.device_name}",
            "Firebase Database: configured",
            "Supabase Storage: configured",
            f"Windows Package: {win_desc}",
            f"Android APK: {android_desc}",
            "Builder Version: 1.0.0",
            f"Build Date: {datetime.datetime.now().isoformat()}",
            "=================================================="
        ]
        (self.output_dir / "Build-Info.txt").write_text("\n".join(info_lines), encoding="utf-8")

    def _cleanup_workspace(self) -> bool:
        """Removes temporary workspace files."""
        try:
            if self.workspace_dir.exists():
                shutil.rmtree(self.workspace_dir, ignore_errors=True)
            return not self.workspace_dir.exists()
        except Exception:
            return False
