use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

use tauri::menu::{CheckMenuItemBuilder, MenuBuilder, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, EventTarget, Manager};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

const MAIN_WINDOW_LABEL: &str = "main";
const TRAY_MENU_SHOW_HIDE: &str = "tray-show-hide";
const TRAY_MENU_AUTOSTART: &str = "tray-autostart";
const TRAY_MENU_RESET_POSITION: &str = "tray-reset-position";
const TRAY_MENU_CHECK_CORE: &str = "tray-check-core";
const TRAY_MENU_QUIT: &str = "tray-quit";
const TRAY_EVENT_RESET_POSITION: &str = "kaka-tray-reset-position";
const TRAY_EVENT_CHECK_CORE: &str = "kaka-tray-check-core";

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    exit_app(&app);
}

#[tauri::command]
fn check_kaka_core_health() -> Result<(), String> {
    let mut stream = TcpStream::connect_timeout(
        &"127.0.0.1:8001"
            .parse()
            .map_err(|error| format!("invalid address: {error}"))?,
        Duration::from_millis(900),
    )
    .map_err(|error| format!("connect failed: {error}"))?;

    stream
        .set_read_timeout(Some(Duration::from_millis(900)))
        .map_err(|error| format!("set read timeout failed: {error}"))?;
    stream
        .set_write_timeout(Some(Duration::from_millis(900)))
        .map_err(|error| format!("set write timeout failed: {error}"))?;

    stream
        .write_all(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1:8001\r\nConnection: close\r\n\r\n")
        .map_err(|error| format!("request failed: {error}"))?;

    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("response failed: {error}"))?;

    if response.starts_with("HTTP/1.1 200") && response.contains("\"status\":\"ok\"") {
        Ok(())
    } else {
        Err("unexpected health response".to_string())
    }
}

fn exit_app(app: &tauri::AppHandle) {
    app.exit(0);
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn toggle_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
        match window.is_visible() {
            Ok(true) => {
                let _ = window.hide();
            }
            _ => {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }
    }
}

fn emit_tray_event(app: &tauri::AppHandle, event_name: &str) {
    show_main_window(app);
    let _ = app.emit_to(
        EventTarget::webview_window(MAIN_WINDOW_LABEL),
        event_name,
        (),
    );
}

fn toggle_autostart(app: &tauri::AppHandle, menu_item: &tauri::menu::CheckMenuItem<tauri::Wry>) {
    let autolaunch = app.autolaunch();
    let next_enabled = !autolaunch.is_enabled().unwrap_or(false);
    let result = if next_enabled {
        autolaunch.enable()
    } else {
        autolaunch.disable()
    };

    if result.is_ok() {
        let _ = menu_item.set_checked(next_enabled);
    } else if let Ok(current_enabled) = autolaunch.is_enabled() {
        let _ = menu_item.set_checked(current_enabled);
    }
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show_hide = MenuItemBuilder::with_id(TRAY_MENU_SHOW_HIDE, "显示/隐藏卡咔").build(app)?;
    let autostart_enabled = app.autolaunch().is_enabled().unwrap_or(false);
    let autostart = CheckMenuItemBuilder::with_id(TRAY_MENU_AUTOSTART, "开机自启")
        .checked(autostart_enabled)
        .build(app)?;
    let reset_position =
        MenuItemBuilder::with_id(TRAY_MENU_RESET_POSITION, "重置位置").build(app)?;
    let check_core = MenuItemBuilder::with_id(TRAY_MENU_CHECK_CORE, "连接测试").build(app)?;
    let quit = MenuItemBuilder::with_id(TRAY_MENU_QUIT, "退出").build(app)?;

    let menu = MenuBuilder::new(app)
        .item(&show_hide)
        .item(&autostart)
        .separator()
        .item(&reset_position)
        .item(&check_core)
        .separator()
        .item(&quit)
        .build()?;

    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/icon.ico"))?;
    let autostart_for_menu = autostart.clone();

    TrayIconBuilder::with_id("kaka-main-tray")
        .tooltip("卡咔桌宠")
        .icon(icon)
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            ) {
                toggle_main_window(tray.app_handle());
            }
        })
        .on_menu_event(move |app, event| match event.id().as_ref() {
            TRAY_MENU_SHOW_HIDE => toggle_main_window(app),
            TRAY_MENU_AUTOSTART => toggle_autostart(app, &autostart_for_menu),
            TRAY_MENU_RESET_POSITION => emit_tray_event(app, TRAY_EVENT_RESET_POSITION),
            TRAY_MENU_CHECK_CORE => emit_tray_event(app, TRAY_EVENT_CHECK_CORE),
            TRAY_MENU_QUIT => exit_app(app),
            _ => {}
        })
        .build(app)?;

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        .setup(|app| {
            setup_tray(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![check_kaka_core_health, quit_app])
        .run(tauri::generate_context!())
        .expect("failed to run Kaka desktop pet");
}
