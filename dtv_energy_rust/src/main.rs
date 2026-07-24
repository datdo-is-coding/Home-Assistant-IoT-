use axum::{
    extract::{Query, State},
    response::{Html, IntoResponse, Json},
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::{net::SocketAddr, sync::Arc};
use tokio::sync::Mutex;
use tower_http::cors::CorsLayer;

#[derive(Clone)]
struct AppState {
    esp_ip: Arc<Mutex<String>>,
    gemini_key: Arc<Mutex<String>>,
    pzem_history: Arc<Mutex<Vec<f32>>>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct EnergyData {
    is_online: bool,
    voltage: String,
    current: String,
    power: String,
    energy: String,
    today: String,
    yesterday: String,
    month: String,
    lastmonth: String,
    money: String,
    lastmoney: String,
    evn_vat_cost: f32,
    power_history: Vec<f32>,
}

#[derive(Deserialize)]
struct IpQuery {
    ip: Option<String>,
}

#[derive(Deserialize)]
struct AiPromptRequest {
    prompt: String,
}

#[derive(Serialize)]
struct AiResponse {
    reply: String,
}

#[tokio::main]
async fn main() {
    println!("🦀 Launching Rust DTV Energy Hub - Liquid Glass Server...");

    let state = AppState {
        esp_ip: Arc::new(Mutex::new("192.168.4.1".to_string())),
        gemini_key: Arc::new(Mutex::new("AIzaSyAC9PKO176Zs6ax3uhq9avfpgOUS215kko".to_string())),
        pzem_history: Arc::new(Mutex::new(vec![0.0; 40])),
    };

    let app = Router::new()
        .route("/", get(serve_liquid_glass_ui))
        .route("/api/data", get(handle_get_data))
        .route("/api/config", post(handle_set_config))
        .route("/api/ai", post(handle_ai_chat))
        .layer(CorsLayer::permissive())
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], 8080));
    println!("🚀 Rust Liquid Glass Server running at: http://localhost:8080");

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn serve_liquid_glass_ui() -> impl IntoResponse {
    Html(include_str!("index.html"))
}

async fn handle_get_data(
    State(state): State<AppState>,
    Query(query): Query<IpQuery>,
) -> impl IntoResponse {
    let mut esp_ip = state.esp_ip.lock().await;
    if let Some(new_ip) = query.ip {
        if !new_ip.trim().is_empty() {
            *esp_ip = new_ip;
        }
    }

    let target_url = format!("http://{}/data", esp_ip.trim());
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_millis(2000))
        .build();

    let mut energy_data = match client {
        Ok(c) => match c.get(&target_url).send().await {
            Ok(resp) => match resp.json::<serde_json::Value>().await {
                Ok(v) => EnergyData {
                    is_online: true,
                    voltage: v.get("voltage").and_then(|x| x.as_str()).unwrap_or("0.0").to_string(),
                    current: v.get("current").and_then(|x| x.as_str()).unwrap_or("0.00").to_string(),
                    power: v.get("power").and_then(|x| x.as_str()).unwrap_or("0").to_string(),
                    energy: v.get("energy").and_then(|x| x.as_str()).unwrap_or("0.0").to_string(),
                    today: v.get("today").and_then(|x| x.as_str()).unwrap_or("0.00").to_string(),
                    yesterday: v.get("yesterday").and_then(|x| x.as_str()).unwrap_or("0.00").to_string(),
                    month: v.get("month").and_then(|x| x.as_str()).unwrap_or("0.00").to_string(),
                    lastmonth: v.get("lastmonth").and_then(|x| x.as_str()).unwrap_or("0.00").to_string(),
                    money: v.get("money").and_then(|x| x.as_str()).unwrap_or("0").to_string(),
                    lastmoney: v.get("lastmoney").and_then(|x| x.as_str()).unwrap_or("0").to_string(),
                    evn_vat_cost: 0.0,
                    power_history: vec![],
                },
                Err(_) => offline_data(),
            },
            Err(_) => offline_data(),
        },
        Err(_) => offline_data(),
    };

    // Calculate EVN 6-Tier Tariff in Rust with 8% VAT
    let month_kwh: f32 = energy_data.month.parse().unwrap_or(0.0);
    energy_data.evn_vat_cost = calculate_evn_vat_rust(month_kwh);

    // Update power history buffer
    let p_val: f32 = energy_data.power.parse().unwrap_or(0.0);
    let mut history = state.pzem_history.lock().await;
    if !history.is_empty() {
        history.remove(0);
    }
    history.push(p_val);
    energy_data.power_history = history.clone();

    Json(energy_data)
}

fn offline_data() -> EnergyData {
    EnergyData {
        is_online: false,
        voltage: "0.0".to_string(),
        current: "0.00".to_string(),
        power: "0".to_string(),
        energy: "0.0".to_string(),
        today: "0.00".to_string(),
        yesterday: "0.00".to_string(),
        month: "0.00".to_string(),
        lastmonth: "0.00".to_string(),
        money: "0".to_string(),
        lastmoney: "0".to_string(),
        evn_vat_cost: 0.0,
        power_history: vec![],
    }
}

// EVN 6-Tier Tariff Calculation Algorithm in Rust
fn calculate_evn_vat_rust(kwh: f32) -> f32 {
    let mut remaining = kwh;
    let mut cost = 0.0;

    let t1 = remaining.min(50.0);
    cost += t1 * 1893.0;
    remaining = (remaining - t1).max(0.0);

    let t2 = remaining.min(50.0);
    cost += t2 * 1956.0;
    remaining = (remaining - t2).max(0.0);

    let t3 = remaining.min(100.0);
    cost += t3 * 2271.0;
    remaining = (remaining - t3).max(0.0);

    let t4 = remaining.min(100.0);
    cost += t4 * 2860.0;
    remaining = (remaining - t4).max(0.0);

    let t5 = remaining.min(100.0);
    cost += t5 * 3197.0;
    remaining = (remaining - t5).max(0.0);

    cost += remaining * 3302.0;

    cost * 1.08 // Include 8% VAT
}

#[derive(Deserialize)]
struct ConfigReq {
    esp_ip: Option<String>,
    gemini_key: Option<String>,
}

async fn handle_set_config(
    State(state): State<AppState>,
    Json(payload): Json<ConfigReq>,
) -> impl IntoResponse {
    if let Some(ip) = payload.esp_ip {
        if !ip.trim().is_empty() {
            *state.esp_ip.lock().await = ip;
        }
    }
    if let Some(key) = payload.gemini_key {
        if !key.trim().is_empty() {
            *state.gemini_key.lock().await = key;
        }
    }
    Json(serde_json::json!({"status": "ok"}))
}

async fn handle_ai_chat(
    State(state): State<AppState>,
    Json(payload): Json<AiPromptRequest>,
) -> impl IntoResponse {
    let active_key = state.gemini_key.lock().await.clone();
    let models = vec!["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-flash-latest"];

    let client = reqwest::Client::new();

    for model in models {
        let url = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}",
            model, active_key
        );

        let body = serde_json::json!({
            "contents": [{
                "parts": [{"text": format!("Bạn là DTV Energy AI Rust. Hãy trả lời ngắn gọn tiếng Việt: {}", payload.prompt)}]
            }]
        });

        if let Ok(res) = client.post(&url).json(&body).send().await {
            if res.status().is_success() {
                if let Ok(json_val) = res.json::<serde_json::Value>().await {
                    if let Some(text) = json_val["candidates"][0]["content"]["parts"][0]["text"].as_str() {
                        return Json(AiResponse { reply: text.to_string() });
                    }
                }
            }
        }
    }

    Json(AiResponse {
        reply: "⚠️ Không thể phản hồi từ Gemini AI. Vui lòng kiểm tra lại kết nối mạng hoặc API Key!".to_string(),
    })
}
