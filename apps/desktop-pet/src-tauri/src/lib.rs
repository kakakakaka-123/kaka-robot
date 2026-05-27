use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::Mutex;
use std::time::Duration;

use tauri::menu::{CheckMenuItemBuilder, MenuBuilder, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, EventTarget, Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

const MAIN_WINDOW_LABEL: &str = "main";
const SETTINGS_WINDOW_LABEL: &str = "settings";
const TRAY_MENU_SHOW_HIDE: &str = "tray-show-hide";
const TRAY_MENU_SETTINGS: &str = "tray-settings";
const TRAY_MENU_AUTOSTART: &str = "tray-autostart";
const TRAY_MENU_RESET_POSITION: &str = "tray-reset-position";
const TRAY_MENU_CHECK_CORE: &str = "tray-check-core";
const TRAY_MENU_QUIT: &str = "tray-quit";
const TRAY_EVENT_RESET_POSITION: &str = "kaka-tray-reset-position";
const TRAY_EVENT_CHECK_CORE: &str = "kaka-tray-check-core";

#[derive(Default)]
struct TrayState {
    autostart_item: Mutex<Option<tauri::menu::CheckMenuItem<tauri::Wry>>>,
}

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    exit_app(&app);
}

#[tauri::command]
fn show_settings_window(app: tauri::AppHandle) -> Result<(), String> {
    open_settings_window(&app)
}

#[tauri::command]
fn get_autostart_enabled(app: tauri::AppHandle) -> Result<bool, String> {
    app.autolaunch()
        .is_enabled()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn set_autostart_enabled(app: tauri::AppHandle, enabled: bool) -> Result<bool, String> {
    set_autostart_enabled_internal(&app, enabled)
}

#[tauri::command]
fn center_main_window(app: tauri::AppHandle) -> Result<(), String> {
    app.get_webview_window(MAIN_WINDOW_LABEL)
        .ok_or_else(|| "main window not found".to_string())?
        .center()
        .map_err(|error| error.to_string())
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

fn open_settings_window(app: &tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(SETTINGS_WINDOW_LABEL) {
        window.show().map_err(|error| error.to_string())?;
        window.set_focus().map_err(|error| error.to_string())?;
        return Ok(());
    }

    WebviewWindowBuilder::new(
        app,
        SETTINGS_WINDOW_LABEL,
        WebviewUrl::App("index.html?view=settings".into()),
    )
    .title("卡咔设置")
    .inner_size(420.0, 520.0)
    .resizable(false)
    .decorations(true)
    .center()
    .build()
    .map_err(|error| error.to_string())?;

    Ok(())
}

fn emit_tray_event(app: &tauri::AppHandle, event_name: &str) {
    show_main_window(app);
    let _ = app.emit_to(
        EventTarget::webview_window(MAIN_WINDOW_LABEL),
        event_name,
        (),
    );
}

fn sync_autostart_menu(app: &tauri::AppHandle, enabled: bool) {
    let menu_item = app
        .state::<TrayState>()
        .autostart_item
        .lock()
        .unwrap()
        .clone();
    if let Some(menu_item) = menu_item {
        let _ = menu_item.set_checked(enabled);
    }
}

fn set_autostart_enabled_internal(app: &tauri::AppHandle, enabled: bool) -> Result<bool, String> {
    let autolaunch = app.autolaunch();
    let result = if enabled {
        autolaunch.enable()
    } else {
        autolaunch.disable()
    };

    result.map_err(|error| error.to_string())?;
    let current_enabled = autolaunch
        .is_enabled()
        .map_err(|error| error.to_string())?;
    sync_autostart_menu(app, current_enabled);
    Ok(current_enabled)
}

fn toggle_autostart(app: &tauri::AppHandle) {
    let next_enabled = !app.autolaunch().is_enabled().unwrap_or(false);
    if set_autostart_enabled_internal(app, next_enabled).is_err() {
        if let Ok(current_enabled) = app.autolaunch().is_enabled() {
            sync_autostart_menu(app, current_enabled);
        }
    };
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show_hide = MenuItemBuilder::with_id(TRAY_MENU_SHOW_HIDE, "显示/隐藏卡咔").build(app)?;
    let settings = MenuItemBuilder::with_id(TRAY_MENU_SETTINGS, "设置").build(app)?;
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
        .item(&settings)
        .item(&autostart)
        .separator()
        .item(&reset_position)
        .item(&check_core)
        .separator()
        .item(&quit)
        .build()?;

    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/icon.ico"))?;
    app.state::<TrayState>()
        .autostart_item
        .lock()
        .unwrap()
        .replace(autostart.clone());

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
            TRAY_MENU_SETTINGS => {
                let _ = open_settings_window(app);
            }
            TRAY_MENU_AUTOSTART => toggle_autostart(app),
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
        .manage(TrayState::default())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        .setup(|app| {
            setup_tray(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            center_main_window,
            check_kaka_core_health,
            get_autostart_enabled,
            quit_app,
            set_autostart_enabled,
            show_settings_window
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Kaka desktop pet");
}
