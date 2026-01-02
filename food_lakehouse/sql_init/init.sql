CREATE TABLE IF NOT EXISTS user_configs (
    id SERIAL PRIMARY KEY,
    user_name VARCHAR(50) DEFAULT 'Thaya',
    target_location VARCHAR(50),
    budget_type VARCHAR(20),
    budget_amount DECIMAL(12,2),
    updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO user_configs (user_name, target_location, budget_type, budget_amount)
SELECT 'Thaya', 'Banjarmasin', 'Monthly', 1500000
WHERE NOT EXISTS (SELECT 1 FROM user_configs);

CREATE TABLE IF NOT EXISTS silver_weather (
    log_id VARCHAR(50) PRIMARY KEY,
    timestamp TIMESTAMP,
    city VARCHAR(50),
    condition VARCHAR(50),
    temp DECIMAL(5,2)
);

CREATE TABLE IF NOT EXISTS gold_recommendations (
    rec_id SERIAL PRIMARY KEY,
    generated_at TIMESTAMP,
    weather_condition VARCHAR(50),
    current_budget_status VARCHAR(50),
    promo_info TEXT,
    recommendation TEXT,
    logic_explanation TEXT
);