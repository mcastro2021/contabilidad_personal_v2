# 🚀 Smart Finance Pro 2026

**Smart Finance Pro 2026** es una plataforma de gestión financiera personal desarrollada en Python y Streamlit, diseñada específicamente para el contexto económico de Argentina. Esta herramienta permite centralizar el control de ingresos, gastos y ahorros, con un enfoque especial en la planificación de proyectos a largo plazo, como la construcción y equipamiento de una vivienda.

## 📋 Características Principales

* **Dashboard Analítico:** Visualización en tiempo real del saldo proyectado y patrimonio acumulado mensual.
* **Integración Dólar Blue:** Consumo automático de API para obtener cotizaciones actualizadas (Compra/Venta) y conversión instantánea de activos.
* **Lógica de Ahorro Argentina:** El sistema trata los ahorros como capital positivo que suma al saldo proyectado, ideal para previsiones de fondos de inversión o plazos fijos.
* **Gestión de Obra:** Estructura preparada para el seguimiento detallado de insumos de construcción (bombas presurizadoras, biodigestores, grifería inteligente).
* **UX/UI Profesional:** Interfaz optimizada con gráficos interactivos de **Plotly** y tablas de edición dinámica con validación de datos (Selectbox).
* **Importación Masiva:** Módulo para migrar datos históricos desde Excel de forma transparente.

## 🛠️ Stack Tecnológico

* **Frontend/UI:** Streamlit (Python).
* **Visualización:** Plotly Express.
* **Base de Datos:** SQLite (Arquitectura local con motor de rescate de datos).
* **Procesamiento de Datos:** Pandas / Openpyxl.
* **API:** DolarAPI (Integración financiera).

## 📥 Instalación y Configuración

1. **Clonar el repositorio:**
```bash
git clone https://github.com/tu-usuario/smart-finance-2026.git
cd smart-finance-2026

```


2. **Crear ambiente virtual (Recomendado):**
```bash
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

```


3. **Instalar dependencias:**
```bash
pip install streamlit pandas plotly openpyxl requests

```


4. **Ejecutar la aplicación:**
```bash
streamlit run app.py

```