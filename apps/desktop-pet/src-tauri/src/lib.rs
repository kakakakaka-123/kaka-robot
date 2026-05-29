use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::Command;
use std::sync::Mutex;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::menu::{CheckMenuItemBuilder, MenuBuilder, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, EventTarget, LogicalSize, Manager, Size, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

const MAIN_WINDOW_LABEL: &str = "main";
const SETTINGS_WINDOW_LABEL: &str = "settings";
const TRAY_MENU_SHOW_HIDE: &str = "tray-show-hide";
const TRAY_MENU_SETTINGS: &str = "tray-settings";
const TRAY_MENU_AUTOSTART: &str = "tray-autostart";
const TRAY_MENU_RESET_POSITION: &str = "tray-reset-position";
const TRAY_MENU_REPAIR_WINDOWS: &str = "tray-repair-windows";
const TRAY_MENU_CHECK_CORE: &str = "tray-check-core";
const TRAY_MENU_RESTART_APP: &str = "tray-restart-app";
const TRAY_MENU_QUIT: &str = "tray-quit";
const TRAY_EVENT_RESET_POSITION: &str = "kaka-tray-reset-position";
const TRAY_EVENT_CHECK_CORE: &str = "kaka-tray-check-core";
const FROM_AUTOSTART_ARG: &str = "--from-autostart";
const STARTUP_SETTINGS_FILE_NAME: &str = "desktop-pet-startup.json";

#[derive(Default)]
struct TrayState {
    show_hide_item: Mutex<Option<tauri::menu::MenuItem<tauri::Wry>>>,
    autostart_item: Mutex<Option<tauri::menu::CheckMenuItem<tauri::Wry>>>,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct StartupSettings {
    show_pet_on_autostart: bool,
}

impl Default for StartupSettings {
    fn default() -> Self {
        Self {
            show_pet_on_autostart: false,
        }
    }
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
fn get_main_window_visible(app: tauri::AppHandle) -> Result<bool, String> {
    app.get_webview_window(MAIN_WINDOW_LABEL)
        .ok_or_else(|| "main window not found".to_string())?
        .is_visible()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn set_main_window_visible(app: tauri::AppHandle, visible: bool) -> Result<bool, String> {
    if visible {
        show_main_window(&app);
    } else {
        hide_main_window(&app);
    }

    get_main_window_visible(app)
}

#[tauri::command]
fn set_main_window_always_on_top(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    app.get_webview_window(MAIN_WINDOW_LABEL)
        .ok_or_else(|| "main window not found".to_string())?
        .set_always_on_top(enabled)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn set_main_window_size(app: tauri::AppHandle, size: f64) -> Result<(), String> {
    let clamped_size = size.clamp(220.0, 360.0);
    app.get_webview_window(MAIN_WINDOW_LABEL)
        .ok_or_else(|| "main window not found".to_string())?
        .set_size(Size::Logical(LogicalSize::new(clamped_size, clamped_size)))
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn get_autostart_enabled(app: tauri::AppHandle) -> Result<bool, String> {
    let enabled = app
        .autolaunch()
        .is_enabled()
        .map_err(|error| error.to_string())?;
    sync_autostart_menu(&app, enabled);
    Ok(enabled)
}

#[tauri::command]
fn set_autostart_enabled(app: tauri::AppHandle, enabled: bool) -> Result<bool, String> {
    set_autostart_enabled_internal(&app, enabled)
}

#[tauri::command]
fn get_startup_settings(app: tauri::AppHandle) -> Result<StartupSettings, String> {
    read_startup_settings(&app)
}

#[tauri::command]
fn set_startup_settings(
    app: tauri::AppHandle,
    settings: StartupSettings,
) -> Result<StartupSettings, String> {
    write_startup_settings(&app, settings)?;
    Ok(settings)
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

fn restart_app(app: &tauri::AppHandle) -> Result<(), String> {
    let exe_path = std::env::current_exe().map_err(|error| error.to_string())?;
    Command::new(exe_path)
        .spawn()
        .map_err(|error| error.to_string())?;
    app.exit(0);
    Ok(())
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
        let _ = window.show();
        let _ = window.set_focus();
        sync_main_window_menu(app, true);
    }
}

fn hide_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
        let _ = window.hide();
        sync_main_window_menu(app, false);
    }
}

fn is_started_from_autostart() -> bool {
    std::env::args().any(|arg| arg == FROM_AUTOSTART_ARG)
}

fn startup_settings_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_config_dir()
        .map_err(|error| error.to_string())?
        .join(STARTUP_SETTINGS_FILE_NAME))
}

fn read_startup_settings(app: &tauri::AppHandle) -> Result<StartupSettings, String> {
    let path = startup_settings_path(app)?;
    if !path.exists() {
        return Ok(StartupSettings::default());
    }

    let raw_value = fs::read_to_string(path).map_err(|error| error.to_string())?;
    serde_json::from_str(&raw_value).map_err(|error| error.to_string())
}

fn write_startup_settings(
    app: &tauri::AppHandle,
    settings: StartupSettings,
) -> Result<(), String> {
    let path = startup_settings_path(app)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }

    let raw_value = serde_json::to_string_pretty(&settings).map_err(|error| error.to_string())?;
    fs::write(path, raw_value).map_err(|error| error.to_string())
}

fn apply_initial_main_window_visibility(app: &tauri::AppHandle) {
    let should_show = !is_started_from_autostart()
        || read_startup_settings(app)
            .map(|settings| settings.show_pet_on_autostart)
            .unwrap_or(false);

    if should_show {
        show_main_window(app);
    } else {
        sync_main_window_menu(app, false);
    }
}

fn toggle_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
        match window.is_visible() {
            Ok(true) => {
                hide_main_window(app);
            }
            _ => {
                let _ = window.show();
                let _ = window.set_focus();
                sync_main_window_menu(app, true);
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

    Err("settings window not found".to_string())
}

fn repair_windows(app: &tauri::AppHandle) {
    if let Some(settings_window) = app.get_webview_window(SETTINGS_WINDOW_LABEL) {
        let _ = settings_window.hide();
        let _ = settings_window.center();
    }

    if let Some(main_window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
        let _ = main_window.center();
        let _ = main_window.show();
        let _ = main_window.set_focus();
        sync_main_window_menu(app, true);
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

fn sync_main_window_menu(app: &tauri::AppHandle, visible: bool) {
    let menu_item = app
        .state::<TrayState>()
        .show_hide_item
        .lock()
        .unwrap()
        .clone();
    if let Some(menu_item) = menu_item {
        let text = if visible { "隐藏卡咔" } else { "显示卡咔" };
        let _ = menu_item.set_text(text);
    }
}

fn set_autostart_enabled_internal(app: &tauri::AppHandle, enabled: bool) -> Result<bool, String> {
    let autolaunch = app.autolaunch();
    let result = if enabled {
        let _ = autolaunch.disable();
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

fn refresh_autostart_registration(app: &tauri::AppHandle) {
    if app.autolaunch().is_enabled().unwrap_or(false) {
        let _ = set_autostart_enabled_internal(app, true);
    }
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
    let show_hide = MenuItemBuilder::with_id(TRAY_MENU_SHOW_HIDE, "显示卡咔").build(app)?;
    let settings = MenuItemBuilder::with_id(TRAY_MENU_SETTINGS, "设置").build(app)?;
    let autostart_enabled = app.autolaunch().is_enabled().unwrap_or(false);
    let autostart = CheckMenuItemBuilder::with_id(TRAY_MENU_AUTOSTART, "开机自启")
        .checked(autostart_enabled)
        .build(app)?;
    let reset_position =
        MenuItemBuilder::with_id(TRAY_MENU_RESET_POSITION, "重置位置").build(app)?;
    let repair_windows_item =
        MenuItemBuilder::with_id(TRAY_MENU_REPAIR_WINDOWS, "修复窗口").build(app)?;
    let check_core = MenuItemBuilder::with_id(TRAY_MENU_CHECK_CORE, "连接测试").build(app)?;
    let restart_app_item = MenuItemBuilder::with_id(TRAY_MENU_RESTART_APP, "重启桌宠").build(app)?;
    let quit = MenuItemBuilder::with_id(TRAY_MENU_QUIT, "退出").build(app)?;

    let menu = MenuBuilder::new(app)
        .item(&show_hide)
        .item(&settings)
        .item(&autostart)
        .separator()
        .item(&reset_position)
        .item(&repair_windows_item)
        .item(&check_core)
        .separator()
        .item(&restart_app_item)
        .item(&quit)
        .build()?;

    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/icon.ico"))?;
    app.state::<TrayState>()
        .autostart_item
        .lock()
        .unwrap()
        .replace(autostart.clone());
    app.state::<TrayState>()
        .show_hide_item
        .lock()
        .unwrap()
        .replace(show_hide.clone());

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
            TRAY_MENU_REPAIR_WINDOWS => repair_windows(app),
            TRAY_MENU_CHECK_CORE => emit_tray_event(app, TRAY_EVENT_CHECK_CORE),
            TRAY_MENU_RESTART_APP => {
                let _ = restart_app(app);
            }
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
            Some(vec![FROM_AUTOSTART_ARG]),
        ))
        .setup(|app| {
            setup_tray(app)?;
            refresh_autostart_registration(app.handle());
            apply_initial_main_window_visibility(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            center_main_window,
            check_kaka_core_health,
            get_autostart_enabled,
            get_main_window_visible,
            get_startup_settings,
            quit_app,
            set_autostart_enabled,
            set_main_window_always_on_top,
            set_main_window_size,
            set_main_window_visible,
            set_startup_settings,
            show_settings_window
        ])
        .on_window_event(|window, event| {
            if window.label() == SETTINGS_WINDOW_LABEL {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("failed to run Kaka desktop pet");
}
