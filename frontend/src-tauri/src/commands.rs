use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
pub struct ApiResponse {
    pub data: serde_json::Value,
    pub status: u16,
}

#[tauri::command]
pub async fn api_request(
    method: String,
    path: String,
    body: Option<String>,
) -> Result<ApiResponse, String> {
    let port = crate::sidecar::get_port();
    let url = format!("http://127.0.0.1:{}/api/v1{}", port, path);

    let client = reqwest::Client::new();
    let mut request = match method.to_uppercase().as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url),
        "PUT" => client.put(&url),
        "DELETE" => client.delete(&url),
        "PATCH" => client.patch(&url),
        _ => return Err(format!("Unsupported method: {}", method)),
    };

    request = request.header("Content-Type", "application/json");

    if let Some(body_str) = body {
        request = request.body(body_str);
    }

    let response = request.send().await.map_err(|e| e.to_string())?;
    let status = response.status().as_u16();
    let data: serde_json::Value = response.json().await.map_err(|e| e.to_string())?;

    Ok(ApiResponse { data, status })
}

#[tauri::command]
pub fn get_sidecar_port() -> u16 {
    crate::sidecar::get_port()
}

#[tauri::command]
pub fn get_sidecar_status() -> String {
    if crate::sidecar::is_running() {
        "running".to_string()
    } else {
        "stopped".to_string()
    }
}
