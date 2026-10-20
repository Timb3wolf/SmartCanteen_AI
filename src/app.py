import sys
from pathlib import Path
import streamlit as st
import pandas as pd

# Ensure project root is in sys.path for direct module execution
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import (
    DATASET_PATH,
    REGRESSION_MODEL_PATH,
    CLASSIFIER_MODEL_PATH,
    REGRESSION_FEATURES_PATH,
    CLASSIFICATION_FEATURES_PATH,
)
from src.utils import (
    load_dataset,
    load_models,
    load_features,
    predict_food_waste_and_risk,
)

# Page configuration (must be first Streamlit call)
st.set_page_config(
    page_title="SmartCanteen AI",
    page_icon="🍽️",
    layout="wide"
)

# Load dataset and models using centralized config paths
df = load_dataset(DATASET_PATH)
rf_model, rf_classifier = load_models(REGRESSION_MODEL_PATH, CLASSIFIER_MODEL_PATH)
regression_features, classification_features = load_features(
    REGRESSION_FEATURES_PATH, CLASSIFICATION_FEATURES_PATH
)

# Sidebar filters
st.sidebar.header("🔎 Dashboard Filters")

selected_meal = st.sidebar.multiselect(
    "Select Meal",
    options=df["Meal"].unique(),
    default=df["Meal"].unique()
)

selected_section = st.sidebar.multiselect(
    "Select Canteen Section",
    options=df["Canteen_Section"].unique(),
    default=df["Canteen_Section"].unique()
)

selected_category = st.sidebar.multiselect(
    "Select Food Category",
    options=df["Food_Category"].unique(),
    default=df["Food_Category"].unique()
)

st.sidebar.divider()

if st.sidebar.button("🔄 Reset Filters"):
    st.rerun()

# Apply filters
filtered_df = df[
    (df["Meal"].isin(selected_meal)) &
    (df["Canteen_Section"].isin(selected_section)) &
    (df["Food_Category"].isin(selected_category))
]

# Title
st.title("🍽️ SmartCanteen AI")

st.markdown(
    "### Predicting Food Waste and Financial Loss for Sustainable University Dining"
)

st.write(
    "SmartCanteen AI analyzes university canteen data to identify "
    "food-waste patterns, financial losses, and waste-risk levels "
    "using data analytics and machine learning."
)

st.divider()

# ==============================
# ML PREDICTION SECTION
# ==============================

st.header("🤖 AI-Powered Food Waste Prediction")

st.write(
    "Enter the date, meal, canteen section, food category, and unit price "
    "to estimate food waste and classify the expected waste-risk level."
)

st.caption(
    "The predictions are generated using your trained Random Forest models."
)

prediction_date = st.date_input(
    "Select Date"
)

prediction_meal = st.selectbox(
    "Select Meal",
    options=df["Meal"].unique()
)

prediction_section = st.selectbox(
    "Select Canteen Section",
    options=df["Canteen_Section"].unique()
)

prediction_category = st.selectbox(
    "Select Food Category",
    options=df["Food_Category"].unique()
)

prediction_price = st.number_input(
    "Unit Price per kg",
    min_value=0.0,
    value=float(df["Unit_Price_per_kg"].mean()),
    step=1.0
)

predict_button = st.button(
    "🔮 Predict Food Waste",
    type="primary"
)

# Prediction history
if "prediction_history" not in st.session_state:
    st.session_state.prediction_history = []

if predict_button:
    # Run model prediction using helper function
    prediction_results = predict_food_waste_and_risk(
        prediction_date=prediction_date,
        prediction_meal=prediction_meal,
        prediction_section=prediction_section,
        prediction_category=prediction_category,
        prediction_price=prediction_price,
        rf_model=rf_model,
        rf_classifier=rf_classifier,
        regression_features=regression_features,
        classification_features=classification_features,
    )

    predicted_waste = prediction_results["predicted_waste"]
    predicted_risk = prediction_results["predicted_risk"]
    estimated_loss = prediction_results["estimated_loss"]

    # Save prediction to history
    st.session_state.prediction_history.append({
        "Date": str(prediction_date),
        "Meal": prediction_meal,
        "Section": prediction_section,
        "Food Category": prediction_category,
        "Unit Price": prediction_price,
        "Predicted Waste (kg)": round(predicted_waste, 2),
        "Risk": predicted_risk,
        "Estimated Loss": round(estimated_loss, 2)
    })

    # Display prediction results
    st.subheader("📊 Prediction Results")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Predicted Food Waste",
            f"{predicted_waste:.2f} kg"
        )

    with col2:
        st.metric(
            "Predicted Waste Risk",
            predicted_risk
        )
    
    with col3:
        st.metric(
            "Estimated Financial Loss",
            f"{estimated_loss:.2f}"
        )    

    if predicted_risk == "Low":
        st.success("Low waste risk")
    elif predicted_risk == "Medium":
        st.warning("Medium waste risk")
    elif predicted_risk == "High":
        st.error("High waste risk")

# Prediction History
if st.session_state.prediction_history:
    st.write("### 📜 Prediction History")

    prediction_history_df = pd.DataFrame(
        st.session_state.prediction_history
    )

    st.dataframe(
        prediction_history_df,
        use_container_width=True
    )

    if st.button("🗑️ Clear Prediction History"):
        st.session_state.prediction_history = []
        st.rerun()

# Calculate KPI values
total_waste = filtered_df["Waste_Weight_kg"].sum()
average_waste = filtered_df["Waste_Weight_kg"].mean()
total_financial_loss = filtered_df["Cost_Loss"].sum()
total_records = len(filtered_df)

# KPI section
st.write("### 📊 Overall Waste Statistics")

st.caption(
    "Key indicators based on the currently selected dashboard filters."
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total Food Waste",
        f"{total_waste:.2f} kg"
    )

with col2:
    st.metric(
        "Average Food Waste",
        f"{average_waste:.2f} kg"
    )

with col3:
    st.metric(
        "Total Financial Loss",
        f"{total_financial_loss:.2f}"
    )

with col4:
    st.metric(
        "Total Records",
        total_records
    )

# Waste by Food Category
st.write("### 🍛 Food Waste by Category")
st.caption("Total food waste generated by each food category.")

waste_by_category = (
    filtered_df.groupby("Food_Category")["Waste_Weight_kg"]
    .sum()
    .sort_values(ascending=False)
)

st.bar_chart(waste_by_category)

# Waste by Meal
st.write("### 🍽️ Food Waste by Meal")
st.caption("Comparison of total food waste across meal periods.")

waste_by_meal = (
    filtered_df.groupby("Meal")["Waste_Weight_kg"]
    .sum()
    .sort_values(ascending=False)
)

st.bar_chart(waste_by_meal)

# Waste by Canteen Section
st.write("### 🏪 Food Waste by Canteen Section")
st.caption("Total food waste generated in each canteen section.")

waste_by_section = (
    filtered_df.groupby("Canteen_Section")["Waste_Weight_kg"]
    .sum()
    .sort_values(ascending=False)
)

st.bar_chart(waste_by_section)

# Financial Loss by Food Category
st.write("### 💰 Financial Loss by Food Category")
st.caption("Estimated financial loss associated with each food category.")

loss_by_category = (
    filtered_df.groupby("Food_Category")["Cost_Loss"]
    .sum()
    .sort_values(ascending=False)
)

st.bar_chart(loss_by_category)

# Waste Risk Distribution
st.write("### ⚠️ Waste Risk Distribution")
st.caption("Distribution of records across Low, Medium, and High waste-risk levels.")

risk_distribution = (
    filtered_df["Waste_Risk"]
    .value_counts()
    .reindex(["Low", "Medium", "High"])
)

st.bar_chart(risk_distribution)

# Dataset Table
st.write("### 📋 Canteen Waste Records")

st.caption(
    "Explore the canteen waste records matching your selected filters."
)

st.dataframe(
    filtered_df,
    use_container_width=True,
    hide_index=True
)

# Waste Trend Over Time
st.write("### 📈 Food Waste Trend Over Time")
st.caption("Daily food-waste trend for the selected filters.")

waste_trend = (
    filtered_df.groupby("Date")["Waste_Weight_kg"]
    .sum()
    .sort_index()
)

st.line_chart(waste_trend)

# Recommendations
st.write("### 💡 Smart Recommendations")

st.caption(
    "Data-driven suggestions to help reduce food waste and financial loss."
)

highest_waste_category = (
    filtered_df.groupby("Food_Category")["Waste_Weight_kg"]
    .sum()
    .idxmax()
)

highest_waste_meal = (
    filtered_df.groupby("Meal")["Waste_Weight_kg"]
    .sum()
    .idxmax()
)

highest_waste_section = (
    filtered_df.groupby("Canteen_Section")["Waste_Weight_kg"]
    .sum()
    .idxmax()
)

highest_loss_category = (
    filtered_df.groupby("Food_Category")["Cost_Loss"]
    .sum()
    .idxmax()
)

st.info(
    f"🍛 Monitor **{highest_waste_category}**, "
    f"which has the highest total food waste in the selected data."
)

st.info(
    f"🍽️ Review preparation and serving patterns during **{highest_waste_meal}**, "
    f"which has the highest total food waste."
)

st.info(
    f"🏪 Give additional attention to **{highest_waste_section}**, "
    f"which has the highest total food waste among the selected sections."
)

st.info(
    f"💰 Focus financial-loss reduction efforts on **{highest_loss_category}**, "
    f"which has the highest total cost loss in the selected data."
)

# Model Performance
st.write("### 🤖 Machine Learning Model Performance")

st.write("#### 🌲 Random Forest Regressor")

regression_metrics = pd.DataFrame({
    "Metric": [
        "Mean Absolute Error (MAE)",
        "Root Mean Squared Error (RMSE)",
        "R² Score"
    ],
    "Value": [
        1.322705,
        1.550671,
        -0.128365
    ]
})

st.dataframe(
    regression_metrics,
    use_container_width=True
)

st.write("#### 🌲 Random Forest Classifier")

classification_metrics = pd.DataFrame({
    "Metric": [
        "Accuracy",
        "Precision",
        "Recall",
        "F1 Score"
    ],
    "Value": [
        0.353846,
        0.354729,
        0.353846,
        0.354169
    ]
})

st.dataframe(
    classification_metrics,
    use_container_width=True
)

st.info(
    "The regression model predicts food waste quantity in kilograms, "
    "while the classification model predicts the waste-risk category. "
    "The displayed values are calculated on the test dataset."
)

st.warning(
    "The current test results indicate that the models have room for improvement. "
    "The negative R² score for regression and approximately 35% classification "
    "accuracy suggest that additional feature engineering and model tuning "
    "could improve predictive performance."
)

# Project Summary
st.write("### 📝 Project Summary")

st.write(
    "SmartCanteen AI uses historical university canteen data to analyze "
    "food waste, financial loss, and waste-risk patterns. The dashboard "
    "provides data visualizations, machine learning predictions, and "
    "recommendations to support sustainable canteen management."
)

st.write(
    "The current system includes food-waste prediction using a Random "
    "Forest Regressor and waste-risk classification using a Random Forest "
    "Classifier. The prediction section also provides an estimated "
    "financial loss based on predicted waste and unit price."
)

# Download Filtered Data
st.write("### 📥 Download Data")

csv_data = filtered_df.to_csv(index=False)

st.download_button(
    label="Download Filtered Data",
    data=csv_data,
    file_name="SmartCanteen_Filtered_Data.csv",
    mime="text/csv"
)

# Footer
st.divider()

st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "<h4>🍽️ SmartCanteen AI</h4>"
    "<p>Machine Learning for Sustainable University Dining</p>"
    "<p>Food Waste Prediction • Risk Classification • Financial Loss Analysis</p>"
    "</div>",
    unsafe_allow_html=True
)

if __name__ == "__main__":
    try:
        from streamlit.runtime import exists as st_runtime_exists
        is_running_in_streamlit = st_runtime_exists()
    except Exception:
        is_running_in_streamlit = False

    if not is_running_in_streamlit:
        print("=" * 60)
        print("SmartCanteen AI Dashboard")
        print("=" * 60)
        print("To launch the Streamlit dashboard, run:")
        print("    streamlit run src/app.py")
        print("or:")
        print("    python -m streamlit run src/app.py")
        print("=" * 60)
