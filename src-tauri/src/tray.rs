use anyhow::Context;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    AppHandle, Manager, Runtime,
};

pub const TRAY_ID: &str = "main-tray";

pub fn create_tray<R: Runtime>(app: &AppHandle<R>) -> anyhow::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示 StoryForge3", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;

    TrayIconBuilder::with_id(TRAY_ID)
        .icon(
            app.default_window_icon()
                .cloned()
                .context("missing default window icon")?,
        )
        .menu(&menu)
        .tooltip("StoryForge3")
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                    #[cfg(target_os = "windows")]
                    {
                        let _ = window.set_skip_taskbar(false);
                    }
                }
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    Ok(())
}
