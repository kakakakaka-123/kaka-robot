use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![check_kaka_core_health, quit_app])
        .run(tauri::generate_context!())
        .expect("failed to run Kaka desktop pet");
}
