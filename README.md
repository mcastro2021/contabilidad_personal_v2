# 💰 CONTABILIDAD PERSONAL V3

Aplicación web integral para la gestión de finanzas personales, control de gastos, ingresos, deudas y proyección financiera. Desarrollada en Python con Streamlit y PostgreSQL.

## ✨ Características Principales

### 📊 1. Dashboard Interactivo
* **KPIs en Tiempo Real:** Visualización inmediata de Resultados (ARS/USD) y Patrimonio Total.
* **Calendario de Mapa de Calor:** Vista mensual interactiva. Los días se oscurecen según la intensidad del gasto. Al hacer clic en un día, se filtran los movimientos de esa fecha.
* **Gráficos Dinámicos:**
    * Distribución de gastos por Grupo (Torta).
    * Gastos por Forma de Pago (Barras).
    * Flujo de caja en Pesos y Dólares (Barras comparativas Ingreso vs Gasto).
* **Listado Detallado:** Tabla jerárquica con semáforos de estado (✅/⏳) y checkbox para marcar "Pagado" rápidamente.

### 📝 2. Gestión de Movimientos
* **CRUD Completo:** Carga, edición y eliminación de registros.
* **Campos Avanzados:** Concepto, **Cuenta o Contrato**, Grupo, Cuotas (actual/total), Moneda (ARS/USD), Forma de Pago.
* **Lógica de Cuotas:** Al cargar una compra en cuotas (ej. 1/12), el sistema proyecta y crea automáticamente los registros futuros en los meses siguientes.
* **Automatizaciones:**
    * Cálculo automático de salarios (basado en lógica SMVM).
    * Actualización automática de valores de activos (ej. Terreno).
    * Actualización en cascada de "Ahorro Mes Anterior".

### 📉 3. Gestión de Deudas
* Módulo específico para registrar deudas totales.
* Registro de pagos parciales que impactan automáticamente en el flujo de caja mensual.
* Barra de progreso visual del pago de la deuda.
* Historial de pagos parciales.

### 🔮 4. Predicciones con IA
* Uso de **Regresión Lineal (Scikit-Learn)** para proyectar gastos futuros basándose en el historial de meses anteriores.

### ⚙️ 5. Configuración y Seguridad
* **Login:** Sistema de autenticación simple con usuario y contraseña hasheada.
* **Backups:**
    * Generación de **SQL Dump** completo (estructura + datos) compatible con migraciones.
    * Exportación a CSV (Excel).
* **Restauración:** Herramienta para restaurar base de datos y corregir secuencias de IDs automáticamente.
* **Notificaciones:** Envío de **Emails automáticos** (vía Gmail SMTP) cada vez que se agrega, edita o paga un movimiento.

---

## 🛠️ Tecnologías Utilizadas

* **Frontend:** [Streamlit](https://streamlit.io/)
* **Base de Datos:** PostgreSQL
* **Visualización:** Plotly Express / Graph Objects
* **Ciencia de Datos:** Pandas, Scikit-Learn, Numpy
* **Backend/Logic:** Python 3.x

---

## 🚀 Puesta en Marcha (Instalación Local)

Sigue estos pasos para ejecutar la aplicación en tu computadora:

### 1. Requisitos Previos
* Tener instalado **Python 3.8+**.
* Tener instalado **PostgreSQL** y **pgAdmin 4**.

### 2. Configurar la Base de Datos
1.  Abre pgAdmin 4.
2.  Crea una nueva base de datos (ej: `contabilidad_local`).
3.  No necesitas crear tablas, la aplicación las crea automáticamente al iniciar (`init_db`).

### 3. Instalación de Dependencias
Abre tu terminal en la carpeta del proyecto y ejecuta:

```bash
pip install streamlit pandas psycopg2-binary requests plotly python-dotenv scikit-learn streamlit-lottie