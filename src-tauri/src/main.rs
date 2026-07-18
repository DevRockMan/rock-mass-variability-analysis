// src-tauri/src/main.rs
// ─────────────────────────────────────────────────────────────────────────────
// Tauri main entry point.
//
// This file is only needed when packaging with Tauri (as an alternative to
// the Electron packaging). The Rust binary is responsible for:
//   1. Finding Python 3 on the host (or using the bundled sidecar)
//   2. Spawning the Streamlit server as a subprocess
//   3. Polling until the server is up, then opening the Tauri window
//   4. Killing the subprocess on window close
//
// Build:
//   cargo tauri build
// ─────────────────────────────────────────────────────────────────────────────

// Prevents an additional console window on Windows in release mode.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    net::TcpListener,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};

use tauri::{
    AppHandle, Manager, RunEvent, WindowEvent,
};

// ── State ─────────────────────────────────────────────────────────────────
struct StreamlitState {
    process: Arc<Mutex<Option<Child>>>,
    port:    u16,
}

// ── Find a free port ───────────────────────────────────────────────────────
fn find_free_port(start: u16, end: u16) -> Option<u16> {
    (start..=end).find(|&p| TcpListener::bind(("127.0.0.1", p)).is_ok())
}

// ── Locate Python 3 ────────────────────────────────────────────────────────
fn find_python(resource_dir: &PathBuf) -> Option<PathBuf> {
    // 1. Bundled venv
    let bundled = if cfg!(target_os = "windows") {
        resource_dir.join("app").join("venv").join("Scripts").join("python.exe")
    } else {
        resource_dir.join("app").join("venv").join("bin").join("python3")
    };
    if bundled.exists() {
        return Some(bundled);
    }

    // 2. System candidates
    let candidates: &[&str] = if cfg!(target_os = "windows") {
        &["python", "python3", "py"]
    } else {
        &["python3", "python3.12", "python3.11", "python3.10", "python"]
    };

    for &cmd in candidates {
        if let Ok(out) = Command::new(cmd).arg("--version").output() {
            let ver = String::from_utf8_lossy(&out.stdout);
            if ver.starts_with("Python 3") {
                return Some(PathBuf::from(cmd));
            }
        }
    }

    None
}

// ── Wait for Streamlit to be ready ────────────────────────────────────────
fn wait_for_server(port: u16, max_tries: u32) -> bool {
    for _ in 0..max_tries {
        if TcpListener::bind(("127.0.0.1", port)).is_err() {
            // Something is now listening on the port — server is up
            return true;
        }
        thread::sleep(Duration::from_millis(800));
    }
    false
}

// ── Tauri commands ─────────────────────────────────────────────────────────
#[tauri::command]
fn get_server_port(state: tauri::State<'_, StreamlitState>) -> u16 {
    state.port
}

#[tauri::command]
async fn open_external(url: String) -> Result<(), String> {
    open::that(&url).map_err(|e| e.to_string())
}

// ── Main ───────────────────────────────────────────────────────────────────
fn main() {
    let process_handle: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let process_handle_cleanup = Arc::clone(&process_handle);

    tauri::Builder::default()
        .setup(move |app| {
            let resource_dir = app.path().resource_dir()
                .expect("Could not get resource directory");

            // 1. Port
            let port = find_free_port(8501, 8599)
                .expect("No free port available in range 8501–8599");

            // 2. Python
            let python = find_python(&resource_dir)
                .expect("Python 3 not found. Please install Python 3.10+ from https://python.org");

            // 3. App script
            let script = resource_dir.join("app").join("rock_mass_variability_analysis.py");
            assert!(script.exists(), "App script not found: {}", script.display());

            // 4. Spawn Streamlit
            println!("Starting Streamlit on port {port} with {}", python.display());
            let child = Command::new(&python)
                .args([
                    "-m", "streamlit", "run",
                    script.to_str().unwrap(),
                    "--server.port",       &port.to_string(),
                    "--server.address",    "127.0.0.1",
                    "--server.headless",   "true",
                    "--server.enableCORS", "false",
                    "--browser.gatherUsageStats", "false",
                ])
                .env("STREAMLIT_SERVER_HEADLESS", "true")
                .env("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
                .env("STREAMLIT_THEME_BASE", "dark")
                .env("STREAMLIT_THEME_PRIMARY_COLOR", "#e8a020")
                .env("STREAMLIT_THEME_BACKGROUND_COLOR", "#080c10")
                .env("STREAMLIT_THEME_SECONDARY_BACKGROUND_COLOR", "#0e1318")
                .env("STREAMLIT_THEME_TEXT_COLOR", "#d8e4f0")
                .stdout(Stdio::inherit())
                .stderr(Stdio::inherit())
                .spawn()
                .expect("Failed to spawn Streamlit process");

            *process_handle.lock().unwrap() = Some(child);

            // 5. Wait for server
            let ready = wait_for_server(port, 60);
            assert!(ready, "Streamlit server failed to start within 60 seconds.");

            // 6. Navigate the main window
            let main_window = app.get_webview_window("main")
                .expect("Main window not found");
            main_window
                .eval(&format!("window.location.replace('http://127.0.0.1:{port}')"))
                .unwrap();

            app.manage(StreamlitState {
                process: Arc::clone(&process_handle),
                port,
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_server_port, open_external])
        .on_window_event(move |_window, event| {
            if let WindowEvent::Destroyed = event {
                // Kill Streamlit on window close
                if let Ok(mut lock) = process_handle_cleanup.lock() {
                    if let Some(ref mut child) = *lock {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("Error running Tauri application");
}
