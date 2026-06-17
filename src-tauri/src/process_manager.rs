use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use anyhow::Context;
use reqwest::Client;

#[cfg(target_os = "windows")]
const TARGET_TRIPLE: &str = "x86_64-pc-windows-msvc";
const SIDECAR_BASE_NAME: &str = "storyforge3-api";

pub struct ProcessManager {
    process: Mutex<Option<Child>>,
    port: u16,
    api_base: String,
}

impl ProcessManager {
    pub fn new(port: u16) -> Self {
        let api_base = format!("http://127.0.0.1:{port}");
        Self {
            process: Mutex::new(None),
            port,
            api_base,
        }
    }

    pub fn start(&self, project_dir: &Path) -> anyhow::Result<()> {
        if let Some(sidecar_path) = Self::find_sidecar(project_dir) {
            log::info!("Starting StoryForge3 API sidecar: {}", sidecar_path.display());

            let port = self.port.to_string();
            let child = Command::new(&sidecar_path)
                .args([&port])
                .env("PYTHONUNBUFFERED", "1")
                .current_dir(project_dir)
                .spawn()
                .with_context(|| {
                    format!("Failed to start sidecar: {}", sidecar_path.display())
                })?;

            *self.process.lock().expect("process mutex poisoned") = Some(child);
            return Ok(());
        }

        let python_path = Self::find_python(project_dir)?;

        log::info!(
            "Starting Python API server (dev mode): {} -m storyforge3 serve --port {}",
            python_path.display(),
            self.port
        );

        let port = self.port.to_string();
        let child = Command::new(&python_path)
            .args(["-m", "storyforge3", "serve", "--port", &port])
            .env("PYTHONUNBUFFERED", "1")
            .current_dir(project_dir)
            .spawn()
            .with_context(|| {
                format!(
                    "Failed to start Python API server with {}",
                    python_path.display()
                )
            })?;

        *self.process.lock().expect("process mutex poisoned") = Some(child);
        Ok(())
    }

    pub async fn wait_for_health(&self, timeout_secs: u64) -> anyhow::Result<()> {
        let client = Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
            .context("Failed to create health-check HTTP client")?;
        let url = format!("{}/api/health", self.api_base);
        let start = Instant::now();
        let timeout = Duration::from_secs(timeout_secs);

        loop {
            match client.get(&url).send().await {
                Ok(response) if response.status().is_success() => {
                    log::info!(
                        "Python API server is healthy after {}ms",
                        start.elapsed().as_millis()
                    );
                    return Ok(());
                }
                Ok(response) => {
                    log::debug!("Python API health check returned {}", response.status());
                }
                Err(error) => {
                    log::debug!("Python API health check not ready: {error}");
                }
            }

            if start.elapsed() >= timeout {
                anyhow::bail!("Python API server did not become healthy within {timeout_secs}s");
            }

            tokio::time::sleep(Duration::from_millis(500)).await;
        }
    }

    pub fn stop(&self) -> anyhow::Result<()> {
        let mut guard = self.process.lock().expect("process mutex poisoned");
        if let Some(mut child) = guard.take() {
            let pid = child.id();
            log::info!("Stopping Python API server (PID: {})", pid);

            // On Windows, child.kill() only terminates the direct child, leaving
            // grandchild processes (e.g. uvicorn reload workers) as orphans that
            // keep the port open. Use taskkill /T /F to kill the entire process tree.
            #[cfg(target_os = "windows")]
            {
                let kill_result = std::process::Command::new("taskkill")
                    .args(["/PID", &pid.to_string(), "/T", "/F"])
                    .output();

                match kill_result {
                    Ok(output) => {
                        if output.status.success() {
                            log::info!("Process tree killed via taskkill (PID: {})", pid);
                        } else {
                            let stderr = String::from_utf8_lossy(&output.stderr);
                            let stdout = String::from_utf8_lossy(&output.stdout);
                            log::warn!(
                                "taskkill exited non-zero (PID: {}): stdout={}, stderr={}",
                                pid,
                                stdout.trim(),
                                stderr.trim()
                            );
                            // Fallback: try direct kill
                            let _ = child.kill();
                        }
                    }
                    Err(error) => {
                        log::warn!("Failed to run taskkill (PID: {}): {}", pid, error);
                        // Fallback: try direct kill
                        let _ = child.kill();
                    }
                }
                let _ = child.wait();
            }

            #[cfg(not(target_os = "windows"))]
            {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
        Ok(())
    }

    pub fn api_base(&self) -> &str {
        &self.api_base
    }

    pub(crate) fn find_sidecar(project_dir: &Path) -> Option<PathBuf> {
        sidecar_candidates(project_dir)
            .into_iter()
            .find(|candidate| candidate.exists())
    }

    pub(crate) fn find_python(project_dir: &Path) -> anyhow::Result<PathBuf> {
        #[cfg(target_os = "windows")]
        {
            let python = project_dir.join(".venv").join("Scripts").join("python.exe");
            if python.exists() {
                return Ok(python);
            }
        }

        #[cfg(not(target_os = "windows"))]
        {
            let python = project_dir.join(".venv").join("bin").join("python");
            if python.exists() {
                return Ok(python);
            }
        }

        anyhow::bail!(
            "Neither StoryForge3 sidecar binary nor Python virtualenv found under {}. \
             Run scripts/build_sidecar.ps1 or set up .venv before launching desktop mode.",
            project_dir.display()
        )
    }
}

fn sidecar_exe_name() -> String {
    #[cfg(target_os = "windows")]
    {
        format!("{SIDECAR_BASE_NAME}-{TARGET_TRIPLE}.exe")
    }
    #[cfg(not(target_os = "windows"))]
    {
        SIDECAR_BASE_NAME.to_string()
    }
}

fn sidecar_dir_name() -> String {
    #[cfg(target_os = "windows")]
    {
        format!("{SIDECAR_BASE_NAME}-{TARGET_TRIPLE}")
    }
    #[cfg(not(target_os = "windows"))]
    {
        SIDECAR_BASE_NAME.to_string()
    }
}

fn sidecar_candidates(project_dir: &Path) -> Vec<PathBuf> {
    let exe_name = sidecar_exe_name();
    let triple_dir = sidecar_dir_name();
    let mut candidates = Vec::new();

    for base in [
        project_dir.join("src-tauri").join("binaries"),
        project_dir.join("binaries"),
    ] {
        candidates.push(base.join(&triple_dir).join(&exe_name));
        candidates.push(base.join(SIDECAR_BASE_NAME).join(&exe_name));
        candidates.push(base.join(&exe_name));
    }

    candidates
}

impl Drop for ProcessManager {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_creates_manager_with_correct_port() {
        let manager = ProcessManager::new(8000);

        assert_eq!(manager.api_base(), "http://127.0.0.1:8000");
    }

    #[test]
    fn find_python_returns_error_for_missing_venv() {
        let result = ProcessManager::find_python(Path::new("Z:/definitely/missing/storyforge3"));

        assert!(result.is_err());
    }

    #[test]
    fn sidecar_candidates_include_supported_windows_layouts() {
        let root = PathBuf::from("D:/python/Novel/storyforge3");
        let candidates = sidecar_candidates(&root);
        let exe_name = sidecar_exe_name();
        let triple_dir = sidecar_dir_name();

        assert!(candidates.contains(
            &root
                .join("src-tauri")
                .join("binaries")
                .join(&triple_dir)
                .join(&exe_name)
        ));
        assert!(candidates.contains(
            &root
                .join("src-tauri")
                .join("binaries")
                .join(SIDECAR_BASE_NAME)
                .join(&exe_name)
        ));
        assert!(candidates.contains(
            &root
                .join("src-tauri")
                .join("binaries")
                .join(&exe_name)
        ));
    }

    #[test]
    fn find_python_error_mentions_sidecar_and_venv() {
        let result = ProcessManager::find_python(Path::new("Z:/definitely/missing/storyforge3"));
        let message = result.expect_err("missing venv should fail").to_string();

        assert!(message.contains("sidecar"));
        assert!(message.contains(".venv"));
    }
}
