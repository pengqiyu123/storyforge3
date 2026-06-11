mod process_manager;
mod tray;

use std::path::{Path, PathBuf};
use std::sync::Arc;

use process_manager::ProcessManager;
use tauri::{Emitter, Manager, RunEvent};
use tauri_plugin_window_state::{AppHandleExt, StateFlags};

const API_PORT: u16 = 8000;

fn window_state_flags() -> StateFlags {
    StateFlags::POSITION | StateFlags::SIZE | StateFlags::MAXIMIZED
}

fn project_dir_from_current_dir(current_dir: &Path) -> PathBuf {
    if current_dir
        .file_name()
        .is_some_and(|name| name == "src-tauri")
    {
        return current_dir
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| current_dir.to_path_buf());
    }
    current_dir.to_path_buf()
}

fn show_main_window(app_handle: &tauri::AppHandle) {
    if let Some(window) = app_handle.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
        #[cfg(target_os = "windows")]
        {
            let _ = window.set_skip_taskbar(false);
        }
    }
}

fn emit_startup_error(app_handle: &tauri::AppHandle, error: &anyhow::Error) {
    let message = error.to_string();
    let _ = app_handle.emit("python-startup-error", message);
    show_main_window(app_handle);
}

#[tauri::command]
fn get_api_base(state: tauri::State<'_, Arc<ProcessManager>>) -> String {
    state.api_base().to_string()
}

#[tauri::command]
fn get_init_status() -> String {
    "ready".to_string()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let current_dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let project_dir = project_dir_from_current_dir(&current_dir);
    let process_manager = Arc::new(ProcessManager::new(API_PORT));

    let mut builder = tauri::Builder::default();

    #[cfg(any(target_os = "macos", target_os = "windows", target_os = "linux"))]
    {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
                #[cfg(target_os = "windows")]
                {
                    let _ = window.set_skip_taskbar(false);
                }
            }
        }));
    }

    let app = builder
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_state_flags(window_state_flags())
                .build(),
        )
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
                #[cfg(target_os = "windows")]
                {
                    let _ = window.set_skip_taskbar(true);
                }
            }
        })
        .setup({
            let process_manager = Arc::clone(&process_manager);
            let project_dir = project_dir.clone();
            move |app| {
                {
                    use tauri_plugin_log::{Target, TargetKind};

                    let log_dir = dirs::data_dir()
                        .unwrap_or_else(|| PathBuf::from("."))
                        .join("storyforge3")
                        .join("logs");
                    std::fs::create_dir_all(&log_dir)?;

                    app.handle().plugin(
                        tauri_plugin_log::Builder::default()
                            .level(log::LevelFilter::Info)
                            .targets([
                                Target::new(TargetKind::Stdout),
                                Target::new(TargetKind::Folder {
                                    path: log_dir,
                                    file_name: Some("storyforge3".into()),
                                }),
                            ])
                            .build(),
                    )?;
                }

                tray::create_tray(app.handle())?;
                app.manage(Arc::clone(&process_manager));

                let app_handle = app.handle().clone();
                let process_manager = Arc::clone(&process_manager);
                tauri::async_runtime::spawn(async move {
                    if let Err(error) = process_manager.start(&project_dir) {
                        log::error!("Failed to start Python API server: {error:#}");
                        emit_startup_error(&app_handle, &error);
                        return;
                    }

                    match process_manager.wait_for_health(30).await {
                        Ok(()) => {
                            show_main_window(&app_handle);
                        }
                        Err(error) => {
                            log::error!("Python API health check failed: {error:#}");
                            emit_startup_error(&app_handle, &error);
                        }
                    }
                });

                Ok(())
            }
        })
        .invoke_handler(tauri::generate_handler![get_api_base, get_init_status])
        .build(tauri::generate_context!())
        .expect("error while building StoryForge3 desktop app");

    app.run(move |app_handle, event| {
        if let RunEvent::ExitRequested { api, code, .. } = &event {
            if code.is_none() {
                api.prevent_exit();
                return;
            }

            api.prevent_exit();
            app_handle.save_window_state(window_state_flags()).ok();
            process_manager.stop().ok();
            std::process::exit(code.unwrap_or(0));
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn project_dir_uses_parent_when_current_dir_is_src_tauri() {
        let dir = PathBuf::from("D:/python/Novel/storyforge3/src-tauri");

        assert_eq!(
            project_dir_from_current_dir(&dir),
            PathBuf::from("D:/python/Novel/storyforge3")
        );
    }

    #[test]
    fn project_dir_keeps_repo_root() {
        let dir = PathBuf::from("D:/python/Novel/storyforge3");

        assert_eq!(project_dir_from_current_dir(&dir), dir);
    }
}
