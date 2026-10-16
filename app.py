import streamlit as st
import pandas as pd
import pymssql
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import pytz
from fpdf import FPDF
import os
import math

# =====================================================================
# CONFIGURACIÓN DE STREAMLIT
# =====================================================================
st.set_page_config(page_title="Reporte Celda Renault", page_icon="🏭", layout="centered")

st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/b/b7/Renault_2021_Text.svg/512px-Renault_2021_Text.svg.png", width=150)
st.title("Generador de Reportes Gerenciales")
st.markdown("Seleccione el rango de fechas para generar el documento oficial en PDF.")

# Filtros en la pantalla principal
col_fecha1, col_fecha2 = st.columns(2)
fecha_inicio_ui = col_fecha1.date_input("📅 Fecha de Inicio")
fecha_fin_ui = col_fecha2.date_input("📅 Fecha de Fin")

btn_generar = st.button("🚀 Generar Reporte PDF", use_container_width=True, type="primary")

if btn_generar:
    FECHA_INICIO = fecha_inicio_ui.strftime('%Y-%m-%d')
    FECHA_FIN = fecha_fin_ui.strftime('%Y-%m-%d')

    with st.spinner('Extrayendo datos de Wiidem y procesando cálculos...'):
        try:
            # ---------------------------------------------------------
            # CONEXIÓN A BASE DE DATOS (Usando secretos de Streamlit)
            # ---------------------------------------------------------
              conexion = pymssql.connect(
                  server=st.secrets["WIIDEM_SERVER"], 
                  user=st.secrets["WIIDEM_USER"], 
                  password=st.secrets["WIIDEM_PASS"], 
                  database=st.secrets["WIIDEM_DB"],
                  login_timeout=15
              )

            # Consultas SQL
            query_total_grupo = f"SELECT AVG(Oee) AS OEE, AVG(Availability) AS DISPONIBILIDAD, AVG(Performance) AS PERFORMANCE, AVG(Quality) AS CALIDAD FROM PROD_D_05 WHERE Date >= '{FECHA_INICIO}' AND Date <= '{FECHA_FIN}' AND Factory = '4'"
            df_total_grupo = pd.read_sql(query_total_grupo, conexion)

            query_oee = f"SELECT Cell AS MAQUINA, AVG(Oee) AS OEE, AVG(Availability) AS DISPONIBILIDAD, AVG(Performance) AS PERFORMANCE, AVG(Quality) AS CALIDAD FROM PROD_D_03 WHERE Date >= '{FECHA_INICIO}' AND Date <= '{FECHA_FIN}' AND Cell LIKE 'CEL%' GROUP BY Cell ORDER BY Cell"
            df_oee = pd.read_sql(query_oee, conexion)
            
            query_prod_diaria = f"SELECT CAST(Date AS DATE) AS FECHA, Cell AS MAQUINA, Turn AS TURNO, ProductiveTime AS PRODUCTIVO, DownTime AS PARADA FROM PROD_D_02 WHERE Date >= '{FECHA_INICIO}' AND Date <= '{FECHA_FIN}' AND Cell LIKE 'CEL%'"
            df_prod_diaria = pd.read_sql(query_prod_diaria, conexion)
            
            query_horarios_diarios = f"SELECT CAST(Started AS DATE) AS FECHA, Cell AS MAQUINA, Turn AS TURNO, MIN(Started) AS HORA_INICIO, MAX(Finish) AS HORA_CIERRE FROM EVENT_01 WHERE Started >= '{FECHA_INICIO}' AND Started <= '{FECHA_FIN} 23:59:59' AND Cell LIKE 'CEL%' GROUP BY CAST(Started AS DATE), Cell, Turn"
            df_horarios_diarios = pd.read_sql(query_horarios_diarios, conexion)
            
            query_resumen_tiempos = f"SELECT UPPER(et1.Name) AS CategoriaPadre, UPPER(et2.Name) AS CategoriaHijo, SUM(e.Interval) AS MinutosTotales FROM EVENT_01 e LEFT JOIN EventType et1 ON e.EventTypeLevel1 = et1.EventTypeId LEFT JOIN EventType et2 ON e.EventTypeLevel2 = et2.EventTypeId WHERE e.Started >= '{FECHA_INICIO}' AND e.Started <= '{FECHA_FIN} 23:59:59' AND e.Cell LIKE 'CEL%' GROUP BY et1.Name, et2.Name"
            df_resumen_tiempos = pd.read_sql(query_resumen_tiempos, conexion)
            
            query_descansos = f"SELECT CAST(e.Started AS DATE) AS FECHA, e.Cell AS MAQUINA, e.Turn AS TURNO, UPPER(et2.Name) AS CategoriaHijo, SUM(e.Interval) as Minutos FROM EVENT_01 e LEFT JOIN EventType et2 ON e.EventTypeLevel2 = et2.EventTypeId WHERE e.Started >= '{FECHA_INICIO}' AND e.Started <= '{FECHA_FIN} 23:59:59' AND e.Cell LIKE 'CEL%' AND UPPER(et2.Name) IN ('BAÑO', 'REFRIGERIO') GROUP BY CAST(e.Started AS DATE), e.Cell, e.Turn, UPPER(et2.Name)"
            df_descansos = pd.read_sql(query_descansos, conexion)

            query_top_fallas = f"SELECT TOP 15 CASE WHEN COALESCE(et3.Name, et2.Name, et1.Name) = 'NAVE NUEVA' AND e.Cell = 'CEL06' THEN 'Celdas Panasonic' WHEN COALESCE(et3.Name, et2.Name, et1.Name) = 'NAVE NUEVA' THEN 'Celdas KUKA' ELSE COALESCE(et3.Name, et2.Name, et1.Name) END AS NombreFalla, et1.Name AS CategoriaPadre, SUM(e.Interval) AS MinutosPerdidos FROM EVENT_01 e LEFT JOIN EventType et1 ON e.EventTypeLevel1 = et1.EventTypeId LEFT JOIN EventType et2 ON e.EventTypeLevel2 = et2.EventTypeId LEFT JOIN EventType et3 ON e.EventTypeLevel3 = et3.EventTypeId WHERE e.Started >= '{FECHA_INICIO}' AND e.Started <= '{FECHA_FIN} 23:59:59' AND e.Cell LIKE 'CEL%' AND (et1.Name LIKE '%FALLA%' OR et1.Name LIKE '%GESTION%' OR et1.Name LIKE '%CALIDAD%') AND COALESCE(et2.Name, '') NOT LIKE '%REFRIGERIO%' AND COALESCE(et2.Name, '') NOT LIKE '%BAÑO%' AND COALESCE(et2.Name, '') NOT LIKE '%DESCANSO%' GROUP BY CASE WHEN COALESCE(et3.Name, et2.Name, et1.Name) = 'NAVE NUEVA' AND e.Cell = 'CEL06' THEN 'Celdas Panasonic' WHEN COALESCE(et3.Name, et2.Name, et1.Name) = 'NAVE NUEVA' THEN 'Celdas KUKA' ELSE COALESCE(et3.Name, et2.Name, et1.Name) END, et1.Name ORDER BY MinutosPerdidos DESC"
            df_top_fallas = pd.read_sql(query_top_fallas, conexion)

            query_tendencia = f"SELECT e.Cell AS MAQUINA, DATEPART(HOUR, e.Started) AS HORA, SUM(e.Interval) AS MinutosPerdidos FROM EVENT_01 e LEFT JOIN EventType et1 ON e.EventTypeLevel1 = et1.EventTypeId LEFT JOIN EventType et2 ON e.EventTypeLevel2 = et2.EventTypeId WHERE e.Started >= '{FECHA_INICIO}' AND e.Started <= '{FECHA_FIN} 23:59:59' AND e.Cell LIKE 'CEL%' AND (et1.Name LIKE '%FALLA%' OR et1.Name LIKE '%GESTION%' OR et1.Name LIKE '%CALIDAD%') AND COALESCE(et2.Name, '') NOT LIKE '%REFRIGERIO%' AND COALESCE(et2.Name, '') NOT LIKE '%BAÑO%' GROUP BY e.Cell, DATEPART(HOUR, e.Started) ORDER BY HORA"
            df_tendencia = pd.read_sql(query_tendencia, conexion)

            query_resumen_maq = f"SELECT e.Cell AS MAQUINA, UPPER(et1.Name) AS CategoriaPadre, UPPER(et2.Name) AS CategoriaHijo, SUM(e.Interval) AS MinutosTotales FROM EVENT_01 e LEFT JOIN EventType et1 ON e.EventTypeLevel1 = et1.EventTypeId LEFT JOIN EventType et2 ON e.EventTypeLevel2 = et2.EventTypeId WHERE e.Started >= '{FECHA_INICIO}' AND e.Started <= '{FECHA_FIN} 23:59:59' AND e.Cell LIKE 'CEL%' GROUP BY e.Cell, et1.Name, et2.Name"
            df_resumen_maq = pd.read_sql(query_resumen_maq, conexion)

            query_top3_maquina = f"WITH FallasRankeadas AS (SELECT e.Cell AS MAQUINA, CASE WHEN COALESCE(et3.Name, et2.Name, et1.Name) = 'NAVE NUEVA' AND e.Cell = 'CEL06' THEN 'Celdas Panasonic' WHEN COALESCE(et3.Name, et2.Name, et1.Name) = 'NAVE NUEVA' THEN 'Celdas KUKA' ELSE COALESCE(et3.Name, et2.Name, et1.Name) END AS NombreFalla, et1.Name AS CategoriaPadre, SUM(e.Interval) AS Minutos, ROW_NUMBER() OVER(PARTITION BY e.Cell ORDER BY SUM(e.Interval) DESC) as RankFalla FROM EVENT_01 e LEFT JOIN EventType et1 ON e.EventTypeLevel1 = et1.EventTypeId LEFT JOIN EventType et2 ON e.EventTypeLevel2 = et2.EventTypeId LEFT JOIN EventType et3 ON e.EventTypeLevel3 = et3.EventTypeId WHERE e.Started >= '{FECHA_INICIO}' AND e.Started <= '{FECHA_FIN} 23:59:59' AND e.Cell LIKE 'CEL%' AND (et1.Name LIKE '%FALLA%' OR et1.Name LIKE '%GESTION%' OR et1.Name LIKE '%CALIDAD%') AND COALESCE(et2.Name, '') NOT LIKE '%REFRIGERIO%' AND COALESCE(et2.Name, '') NOT LIKE '%BAÑO%' AND COALESCE(et2.Name, '') NOT LIKE '%DESCANSO%' GROUP BY e.Cell, et1.Name, CASE WHEN COALESCE(et3.Name, et2.Name, et1.Name) = 'NAVE NUEVA' AND e.Cell = 'CEL06' THEN 'Celdas Panasonic' WHEN COALESCE(et3.Name, et2.Name, et1.Name) = 'NAVE NUEVA' THEN 'Celdas KUKA' ELSE COALESCE(et3.Name, et2.Name, et1.Name) END) SELECT MAQUINA, NombreFalla, CategoriaPadre, Minutos FROM FallasRankeadas WHERE RankFalla <= 3"
            df_top3_maquina = pd.read_sql(query_top3_maquina, conexion)

            query_dt_area = f"SELECT e.Cell AS MAQUINA, et1.Name AS Nivel1, et2.Name AS Nivel2, SUM(e.Interval) AS Minutos FROM EVENT_01 e LEFT JOIN EventType et1 ON e.EventTypeLevel1 = et1.EventTypeId LEFT JOIN EventType et2 ON e.EventTypeLevel2 = et2.EventTypeId WHERE e.Started >= '{FECHA_INICIO}' AND e.Started <= '{FECHA_FIN} 23:59:59' AND e.Cell LIKE 'CEL%' AND (et1.Name LIKE '%FALLA%' OR et1.Name LIKE '%GESTION%' OR et1.Name LIKE '%CALIDAD%') AND COALESCE(et2.Name, '') NOT LIKE '%REFRIGERIO%' AND COALESCE(et2.Name, '') NOT LIKE '%BAÑO%' AND COALESCE(et2.Name, '') NOT LIKE '%DESCANSO%' GROUP BY e.Cell, et1.Name, et2.Name"
            df_dt_area = pd.read_sql(query_dt_area, conexion)

            query_top_prod = f"WITH ProductoRankeado AS (SELECT Cell AS MAQUINA, Code AS CODIGO_PRODUCTO, SUM(Good) AS BUENAS, SUM(Rework) AS RETRABAJO, SUM(Scrap) AS OBSERVADAS, SUM(Good + Rework + Scrap) AS TOTAL_PRODUCIDO, AVG(CycleTime) AS TC, ROW_NUMBER() OVER(PARTITION BY Cell ORDER BY SUM(Good + Rework + Scrap) DESC) as RankProd FROM PROD_D_01 WHERE Date >= '{FECHA_INICIO}' AND Date <= '{FECHA_FIN}' AND Cell LIKE 'CEL%' GROUP BY Cell, Code) SELECT * FROM ProductoRankeado WHERE RankProd <= 5"
            df_top_prod = pd.read_sql(query_top_prod, conexion)
            
            query_perf_operarios = f"SELECT o.Operator AS Operador, f.Name AS Fabrica, (SELECT STRING_AGG(DISTINCT e.Cell, ', ') FROM EVENT_OPERATOR_01 eo JOIN EVENT_01 e ON eo.EventId = e.Id WHERE eo.OperatorId = o.OperatorId AND e.Started >= '{FECHA_INICIO}' AND e.Started <= '{FECHA_FIN} 23:59:59') AS MaquinasOperadas, AVG(o.Performance) AS Perf FROM OPER_D_01 o LEFT JOIN Factory f ON o.FactoryId = f.FactoryId WHERE o.Date >= '{FECHA_INICIO}' AND o.Date <= '{FECHA_FIN}' GROUP BY o.OperatorId, o.Operator, f.Name ORDER BY Perf DESC"
            try: df_perf_operarios = pd.read_sql(query_perf_operarios, conexion)
            except: df_perf_operarios = pd.DataFrame()

            query_descansos_operarios = f"SELECT op.Name AS Operador, e.Factory AS Fabrica, UPPER(et2.Name) AS TipoDescanso, SUM(e.Interval) AS TotalMin, COUNT(e.Id) AS CantVeces FROM EVENT_01 e JOIN EVENT_OPERATOR_01 eo ON e.Id = eo.EventId JOIN Operator op ON eo.OperatorId = op.OperatorId LEFT JOIN EventType et2 ON e.EventTypeLevel2 = et2.EventTypeId WHERE e.Started >= '{FECHA_INICIO}' AND e.Started <= '{FECHA_FIN} 23:59:59' AND UPPER(et2.Name) IN ('BAÑO', 'REFRIGERIO') GROUP BY op.Name, e.Factory, UPPER(et2.Name) ORDER BY TotalMin DESC"
            try: 
                df_desc_operarios = pd.read_sql(query_descansos_operarios, conexion)
                if not df_desc_operarios.empty: df_desc_operarios['PromedioMin'] = df_desc_operarios['TotalMin'] / df_desc_operarios['CantVeces']
            except: df_desc_operarios = pd.DataFrame()

            conexion.close() 

            # ---------------------------------------------------------
            # PROCESAMIENTO
            # ---------------------------------------------------------
            def formatear_nombre_maq(nombre): return str(nombre).replace('CELDA ', 'Celda 0').replace('CEL', 'Celda ') + ' Fumis'
            def min_a_hhmm_hs(minutos_num):
                if pd.isna(minutos_num) or minutos_num <= 0: return "00:00 hs"
                return f"{int(minutos_num // 60):02d}:{int(minutos_num % 60):02d} hs"

            def get_area(falla, padre):
                f, p = str(falla).upper(), str(padre).upper()
                if 'DEFECTUOSO' in f or 'NO OK' in f or 'RETRABAJO' in f or 'CALIDAD' in p: return 'Calidad'
                elif 'TRAYECTORIA' in f or 'ROBOT' in f or 'TECNOLOG' in f or 'AUTOMATIZACI' in f or 'ESPESOR' in f: return 'Tecnologia'
                elif 'DISPOSITIVO' in f or 'SENSOR' in f or 'BRIDA' in f or 'CALIBRE' in f or 'AJUSTE' in f or 'OPERATIVA' in f: return 'Dispositivo'
                elif 'LOGIST' in f or 'ABAST' in f or 'COMPONENTE' in f or 'MATERIA PRIMA' in f or 'ESTIBADO' in f or 'L13' in f or 'MEDIO' in f: return 'Logistica'
                elif 'MANTENIMIENTO' in f or 'KUKA' in f or 'PANASONIC' in f or 'PICO' in f or 'M2' in f or 'NAVE NUEVA' in f: return 'Mantenimiento'
                elif 'GESTION' in p or 'GESTION' in f: return 'Gestion'
                return 'Mantenimiento'

            df_oee['MAQUINA'] = df_oee['MAQUINA'].apply(formatear_nombre_maq)
            cols_kpi = ['OEE', 'DISPONIBILIDAD', 'PERFORMANCE', 'CALIDAD']
            for col in cols_kpi: df_oee[col] = pd.to_numeric(df_oee[col], errors='coerce').fillna(0.0)
            
            total_grupo = {
                'OEE': df_total_grupo['OEE'].values[0] if not df_total_grupo.empty else 0,
                'DISPONIBILIDAD': df_total_grupo['DISPONIBILIDAD'].values[0] if not df_total_grupo.empty else 0,
                'PERFORMANCE': df_total_grupo['PERFORMANCE'].values[0] if not df_total_grupo.empty else 0,
                'CALIDAD': df_total_grupo['CALIDAD'].values[0] if not df_total_grupo.empty else 0
            }

            apertura_mensual_dict, bano_dict, refri_dict = {}, {}, {}
            if not df_descansos.empty:
                for _, row in df_descansos.iterrows():
                    key = (formatear_nombre_maq(row['MAQUINA']), row['TURNO'])
                    cat = str(row['CategoriaHijo']).upper()
                    if 'BAÑO' in cat: bano_dict[key] = row['Minutos']
                    if 'REFRIGERIO' in cat: refri_dict[key] = row['Minutos']

            if not df_prod_diaria.empty:
                df_prod_diaria['FECHA'] = pd.to_datetime(df_prod_diaria['FECHA'])
                df_horarios_diarios['FECHA'] = pd.to_datetime(df_horarios_diarios['FECHA'])
                df_diario = pd.merge(df_prod_diaria, df_horarios_diarios, on=['FECHA', 'MAQUINA', 'TURNO'], how='left')
                df_diario['MAQUINA'] = df_diario['MAQUINA'].apply(formatear_nombre_maq)
                df_diario['MIN_APERTURA_NETA'] = df_diario['PRODUCTIVO'].fillna(0) + df_diario['PARADA'].fillna(0)
                df_apertura_mensual = df_diario.groupby('MAQUINA')['MIN_APERTURA_NETA'].sum().reset_index()
                for _, row in df_apertura_mensual.iterrows(): apertura_mensual_dict[row['MAQUINA']] = row['MIN_APERTURA_NETA']
                df_diario['HORA_INICIO_DT'], df_diario['HORA_CIERRE_DT'] = pd.to_datetime(df_diario['HORA_INICIO']), pd.to_datetime(df_diario['HORA_CIERRE'])
                df_diario['DURACION_TOTAL'] = (df_diario['HORA_CIERRE_DT'] - df_diario['HORA_INICIO_DT']).dt.total_seconds() / 60.0
                df_diario['MIN_NO_REGISTRADO'] = df_diario['DURACION_TOTAL'] - df_diario['MIN_APERTURA_NETA']
                df_diario.loc[df_diario['MIN_NO_REGISTRADO'] < 0, 'MIN_NO_REGISTRADO'] = 0
                df_diario['INICIO_MIN'] = df_diario['HORA_INICIO_DT'].dt.hour * 60 + df_diario['HORA_INICIO_DT'].dt.minute
                df_diario['CIERRE_MIN'] = df_diario['HORA_CIERRE_DT'].dt.hour * 60 + df_diario['HORA_CIERRE_DT'].dt.minute
                df_turnos = df_diario.groupby(['TURNO', 'MAQUINA']).agg({'INICIO_MIN': 'median', 'CIERRE_MIN': 'median', 'MIN_APERTURA_NETA': 'mean', 'MIN_NO_REGISTRADO': 'mean'}).reset_index()
                def format_hora_habitual(mins): return "-" if pd.isna(mins) else f"{int(mins // 60) % 24:02d}:{int(mins % 60):02d}"
                df_turnos['TXT_INICIO'], df_turnos['TXT_CIERRE'] = df_turnos['INICIO_MIN'].apply(format_hora_habitual), df_turnos['CIERRE_MIN'].apply(format_hora_habitual)
                df_turnos['TXT_APERTURA_NETA'] = df_turnos['MIN_APERTURA_NETA'].apply(min_a_hhmm_hs)
            else: df_turnos = pd.DataFrame()

            tiempos_agrupados = {'Produccion': 0, 'Fallas/Gestion': 0, 'Paradas Prog.': 0, 'Proyecto': 0, 'Descansos': 0}
            if not df_resumen_tiempos.empty:
                for _, row in df_resumen_tiempos.iterrows():
                    cat, subcat = str(row['CategoriaPadre']).upper(), str(row['CategoriaHijo']).upper()
                    mins = row['MinutosTotales'] if not pd.isna(row['MinutosTotales']) else 0
                    if 'REFRIGERIO' in subcat or 'BAÑO' in subcat or 'DESCANSO' in subcat: tiempos_agrupados['Descansos'] += mins
                    elif 'PROYECTO' in subcat: tiempos_agrupados['Proyecto'] += mins
                    elif 'PRODUCCION' in cat: tiempos_agrupados['Produccion'] += mins
                    elif 'PARADA PROGRAMADA' in cat: tiempos_agrupados['Paradas Prog.'] += mins
                    elif 'PROYECTO' in cat: tiempos_agrupados['Proyecto'] += mins
                    elif cat != 'NONE' and cat != 'NAN': tiempos_agrupados['Fallas/Gestion'] += mins

            resumen_maq_dict = {}
            if not df_resumen_maq.empty:
                df_resumen_maq['MAQUINA'] = df_resumen_maq['MAQUINA'].apply(formatear_nombre_maq)
                for _, row in df_resumen_maq.iterrows():
                    m = row['MAQUINA']
                    cat, subcat = str(row['CategoriaPadre']).upper(), str(row['CategoriaHijo']).upper()
                    mins = row['MinutosTotales'] if not pd.isna(row['MinutosTotales']) else 0
                    if m not in resumen_maq_dict: resumen_maq_dict[m] = {'Produccion': 0, 'Fallas': 0, 'ParadaProg': 0, 'Descanso': 0}
                    if 'REFRIGERIO' in subcat or 'BAÑO' in subcat or 'DESCANSO' in subcat: resumen_maq_dict[m]['Descanso'] += mins
                    elif 'PRODUCCION' in cat: resumen_maq_dict[m]['Produccion'] += mins
                    elif 'PARADA PROGRAMADA' in cat: resumen_maq_dict[m]['ParadaProg'] += mins
                    elif 'PROYECTO' not in cat and 'PROYECTO' not in subcat and cat != 'NONE' and cat != 'NAN':
                        resumen_maq_dict[m]['Fallas'] += mins

            top3_dict = {}
            if not df_top3_maquina.empty:
                df_top3_maquina['MAQUINA'] = df_top3_maquina['MAQUINA'].apply(formatear_nombre_maq)
                for _, row in df_top3_maquina.iterrows():
                    m = row['MAQUINA']
                    if m not in top3_dict: top3_dict[m] = []
                    falla, area = str(row['NombreFalla']), get_area(row['NombreFalla'], row['CategoriaPadre'])
                    mins = int(round(row['Minutos'])) if not pd.isna(row['Minutos']) else 0
                    top3_dict[m].append(f"- {area} - {falla[:32]} ({mins}m)")

            areas_dt_dict = {}
            if not df_dt_area.empty:
                for _, row in df_dt_area.iterrows():
                    maq = formatear_nombre_maq(row['MAQUINA'])
                    nivel1, nivel2 = str(row['Nivel1']).upper(), str(row['Nivel2']).upper()
                    mins = float(row['Minutos']) if not pd.isna(row['Minutos']) else 0.0
                    if maq not in areas_dt_dict: areas_dt_dict[maq] = {'MANTEN.': 0, 'DISPOSIT.': 0, 'TECNOL.': 0, 'LOGIST.': 0, 'GESTION': 0, 'CALIDAD': 0}
                    if 'FALLA' in nivel1:
                        if 'DISPOSITIVO' in nivel2: areas_dt_dict[maq]['DISPOSIT.'] += mins
                        elif 'TECNOLOGIA' in nivel2: areas_dt_dict[maq]['TECNOL.'] += mins
                        elif 'LOGISTICA' in nivel2: areas_dt_dict[maq]['LOGIST.'] += mins
                        elif 'MANTENIMIENTO' in nivel2: areas_dt_dict[maq]['MANTEN.'] += mins
                        elif 'GESTION' in nivel2: areas_dt_dict[maq]['GESTION'] += mins
                        elif 'CALIDAD' in nivel2: areas_dt_dict[maq]['CALIDAD'] += mins
                        else: areas_dt_dict[maq]['MANTEN.'] += mins
                    elif 'GESTION' in nivel1: areas_dt_dict[maq]['GESTION'] += mins
                    elif 'CALIDAD' in nivel1: areas_dt_dict[maq]['CALIDAD'] += mins
                    else: areas_dt_dict[maq]['MANTEN.'] += mins 

            if not df_top_prod.empty: df_top_prod['MAQUINA'] = df_top_prod['MAQUINA'].apply(formatear_nombre_maq)

            # ---------------------------------------------------------
            # MATPLOTLIB - GRÁFICOS
            # ---------------------------------------------------------
            if not df_oee.empty:
                try:
                    maquinas = df_oee['MAQUINA'].tolist()
                    fig, ax = plt.subplots(figsize=(10, 3.5)) 
                    x, width = np.arange(len(cols_kpi)), 0.8 / len(maquinas)
                    colores = plt.cm.tab20(np.linspace(0, 1, len(maquinas)))
                    for i, maquina in enumerate(maquinas):
                        rects = ax.bar(x + (i - len(maquinas)/2) * width + width/2, df_oee[df_oee['MAQUINA'] == maquina][cols_kpi].values[0], width, label=maquina, color=colores[i])
                        ax.bar_label(rects, fmt='%.1f', padding=2, rotation=90, fontsize=8, color='black')
                    ax.set_ylabel('Porcentaje (%)'); ax.set_xticks(x); ax.set_xticklabels(cols_kpi); ax.set_ylim(0, df_oee[cols_kpi].max().max() * 1.4)
                    ax.legend(bbox_to_anchor=(0.5, 1.20), loc='upper center', ncol=4, frameon=False, fontsize=8.5)
                    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False); ax.grid(axis='y', linestyle='--', alpha=0.5)
                    plt.tight_layout(); plt.savefig('grafico_kpis.png', dpi=300, bbox_inches='tight'); plt.close()
                except: pass

            if not df_top_fallas.empty:
                try:
                    df_top_fallas['Falla_Completa'] = df_top_fallas.apply(lambda row: get_area(row['NombreFalla'], row['CategoriaPadre']) + ' - ' + str(row['NombreFalla']), axis=1)
                    df_top_fallas = df_top_fallas.sort_values('MinutosPerdidos', ascending=True)
                    fig, ax = plt.subplots(figsize=(7, 4))
                    barras = ax.barh(df_top_fallas['Falla_Completa'].str[:45], df_top_fallas['MinutosPerdidos'], color='#E67E22')
                    for barra in barras: ax.text(barra.get_width() + 5, barra.get_y() + barra.get_height()/2, f"{int(round(barra.get_width()))}m", va='center', ha='left', fontsize=9, color='black')
                    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False); ax.spines['bottom'].set_visible(False); ax.set_xticks([]); ax.tick_params(axis='y', labelsize=8)
                    plt.tight_layout(); plt.savefig('grafico_top_fallas.png', dpi=300, bbox_inches='tight'); plt.close()
                except: pass

            if not df_tendencia.empty:
                try:
                    df_tendencia['MAQUINA'] = df_tendencia['MAQUINA'].apply(formatear_nombre_maq)
                    pivot_tendencia = df_tendencia.pivot(index='HORA', columns='MAQUINA', values='MinutosPerdidos').fillna(0)
                    fig, ax = plt.subplots(figsize=(7, 4))
                    for col in pivot_tendencia.columns: ax.plot(pivot_tendencia.index, pivot_tendencia[col], marker='o', markersize=4, label=col, linewidth=1.5)
                    ax.set_xticks(pivot_tendencia.index); ax.set_xticklabels([f"{int(h):02d}:00" for h in pivot_tendencia.index], fontsize=8, rotation=45); ax.set_ylabel('Min', fontsize=9); ax.tick_params(axis='y', labelsize=8)
                    ax.legend(bbox_to_anchor=(0.5, 1.25), loc='upper center', ncol=2, frameon=False, fontsize=8)
                    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False); ax.grid(color='lightgray', linestyle='-', linewidth=0.5, alpha=0.7)
                    plt.tight_layout(); plt.savefig('grafico_tendencia.png', dpi=300, bbox_inches='tight'); plt.close()
                except: pass

            # ---------------------------------------------------------
            # GENERACIÓN DEL PDF
            # ---------------------------------------------------------
            COLOR_TITULO, COLOR_GRIS, COLOR_NEGRO = (211, 84, 0), (100, 100, 100), (0, 0, 0)
            TARGETS = {'OEE': 80.0, 'DISPONIBILIDAD': 92.0, 'PERFORMANCE': 87.0, 'CALIDAD': 99.5}

            def obtener_color(valor, kpi_name):
                meta = TARGETS.get(kpi_name, 0)
                if pd.isna(valor): return COLOR_NEGRO 
                margen = 0.01 if kpi_name == 'CALIDAD' else 0.05
                tolerancia = meta * margen 
                if valor >= meta: return (40, 167, 69) 
                elif valor >= (meta - tolerancia): return (230, 126, 34) 
                else: return (220, 53, 69) 

            class ReportePDF(FPDF):
                def footer(self):
                    if self.page_no() > 1:
                        self.set_y(-15); self.set_font('Arial', 'I', 8); self.set_text_color(150, 150, 150)
                        self.cell(0, 10, f'Página {self.page_no() - 1} de {{nb}}', 0, 0, 'C')

                def print_kpi(self, etiqueta, valor_num, kpi_name, separador=" | "):
                    color_dinamico = obtener_color(valor_num, kpi_name)
                    valor_txt = f"{valor_num:.1f}%" if not pd.isna(valor_num) else "0.0%"
                    self.set_font("Arial", 'B', 10); self.set_text_color(*COLOR_NEGRO); self.cell(self.get_string_width(etiqueta), 6, txt=etiqueta, ln=0)
                    self.set_text_color(*color_dinamico); self.cell(self.get_string_width(valor_txt), 6, txt=valor_txt, ln=0)
                    self.set_text_color(*COLOR_NEGRO); self.cell(self.get_string_width(separador), 6, txt=separador, ln=0)

            pdf = ReportePDF(orientation='P', unit='mm', format='A4')
            pdf.alias_nb_pages() 
            pdf.set_auto_page_break(auto=True, margin=15) 
            
            # --- PÁGINA 1: PORTADA ---
            pdf.add_page(); pdf.set_font("Arial", 'B', 20); pdf.set_text_color(*COLOR_TITULO)
            pdf.cell(0, 15, txt="REPORTE GERENCIAL - CELDA RENAULT", ln=True, align='R')
            fecha_actual = datetime.now(pytz.timezone('America/Argentina/Cordoba')).strftime("%d/%m/%Y %H:%M")
            texto_periodo = f"Día {FECHA_INICIO}" if FECHA_INICIO == FECHA_FIN else f"Del {FECHA_INICIO} al {FECHA_FIN}"
            pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_GRIS)
            pdf.cell(0, 6, txt=f"Período: {texto_periodo}", ln=True, align='R')
            pdf.set_font("Arial", '', 10); pdf.cell(0, 6, txt=f"Generado el: {fecha_actual}", ln=True, align='R')
            pdf.ln(30); pdf.set_font("Arial", 'B', 18); pdf.set_text_color(*COLOR_TITULO)
            pdf.cell(0, 15, txt="ÍNDICE DEL REPORTE", ln=True, align='C'); pdf.ln(10)

            link_oee = pdf.add_link(); link_kpis = pdf.add_link(); link_horarios = pdf.add_link(); link_resumen_grupo = pdf.add_link(); link_tendencias = pdf.add_link(); link_resumen_maq = pdf.add_link(); link_dt_area = pdf.add_link(); link_prod = pdf.add_link(); link_final = pdf.add_link(); link_anexo = pdf.add_link()

            pdf.set_font("Arial", 'U', 12); pdf.set_text_color(211, 84, 0)
            pdf.cell(0, 8, txt=">> 1. Resumen OEE del Grupo", ln=True, link=link_oee)
            pdf.cell(0, 8, txt=">> 2. Comparativa de KPIs entre Máquinas", ln=True, link=link_kpis)
            pdf.cell(0, 8, txt=">> 3. Horarios y Tiempo de Apertura", ln=True, link=link_horarios)
            pdf.cell(0, 8, txt=">> 4. Resumen Tiempos Grupo", ln=True, link=link_resumen_grupo)
            pdf.cell(0, 8, txt=">> 5. Análisis de Fallas y Tendencias", ln=True, link=link_tendencias)
            pdf.cell(0, 8, txt=">> 6. Cuadro Resumen por Máquinas", ln=True, link=link_resumen_maq)
            pdf.cell(0, 8, txt=">> 7. Distribución de Down Time por Área", ln=True, link=link_dt_area)
            pdf.cell(0, 8, txt=">> 8. Desglose de Producción", ln=True, link=link_prod)
            pdf.cell(0, 8, txt=">> 9. SECCIÓN FINAL: PERFORMANCE Y TIEMPOS", ln=True, link=link_final)
            pdf.cell(0, 8, txt=">> 10. Anexo: Registro Diario Exacto de Apertura y Cierre", ln=True, link=link_anexo)

            # --- PÁGINA 2 ---
            pdf.add_page(); pdf.set_link(link_oee)
            pdf.set_font("Arial", 'B', 14); pdf.set_text_color(*COLOR_TITULO)
            pdf.cell(120, 6, txt="SECCIÓN GRUPO: CELDA RENAULT", ln=0)
            pdf.set_draw_color(150, 150, 150); pdf.line(10, pdf.get_y()+8, 200, pdf.get_y()+8); pdf.ln(10)

            pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
            pdf.cell(0, 6, txt="1. Resumen OEE del Grupo", ln=True)
            pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(2)
            pdf.set_font("Arial", 'B', 9); pdf.set_text_color(*COLOR_GRIS); pdf.cell(0, 5, txt="Objetivos (Target) del mes: OEE: 80.0% | Disp: 92.0% | Perf: 87.0% | Cal: 99.5%", ln=True); pdf.ln(1)

            if not df_oee.empty:
                pdf.set_font("Arial", 'B', 10); pdf.set_text_color(*COLOR_NEGRO)
                pdf.cell(pdf.get_string_width("Total CELDA RENAULT | "), 5, txt="Total CELDA RENAULT | ", ln=0)
                pdf.print_kpi("OEE: ", total_grupo['OEE'], 'OEE')
                pdf.print_kpi("Disp: ", total_grupo['DISPONIBILIDAD'], 'DISPONIBILIDAD')
                pdf.print_kpi("Perf: ", total_grupo['PERFORMANCE'], 'PERFORMANCE')
                pdf.print_kpi("Cal: ", total_grupo['CALIDAD'], 'CALIDAD', separador="")
                pdf.ln(5)
                for _, fila in df_oee.iterrows():
                    pdf.cell(5, 4, txt="", ln=0); txt_nombre = f"> {fila['MAQUINA']} | "
                    pdf.set_font("Arial", 'B', 9.5); pdf.set_text_color(*COLOR_NEGRO); pdf.cell(pdf.get_string_width(txt_nombre), 4, txt=txt_nombre, ln=0)
                    pdf.print_kpi("OEE: ", fila['OEE'], 'OEE'); pdf.print_kpi("Disp: ", fila['DISPONIBILIDAD'], 'DISPONIBILIDAD'); pdf.print_kpi("Perf: ", fila['PERFORMANCE'], 'PERFORMANCE'); pdf.print_kpi("Cal: ", fila['CALIDAD'], 'CALIDAD', separador=""); pdf.ln(4) 
                    
                pdf.ln(3); pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
                pdf.set_link(link_kpis)
                pdf.cell(0, 6, txt="2. Comparativa de KPIs entre Máquinas", ln=True)
                pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(2)
                if os.path.exists('grafico_kpis.png'): pdf.image('grafico_kpis.png', x=10, w=190)

            # --- SECCIÓN 3 ---
            pdf.ln(5)
            if pdf.get_y() > 250: pdf.add_page()
            if not df_turnos.empty:
                pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
                pdf.set_link(link_horarios)
                pdf.cell(0, 6, txt="3. Horarios y Tiempo de Apertura", ln=True)
                pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(2)

                cols_w3 = [45, 14, 25, 25, 30, 25, 25] 
                headers3 = ["Maquina", "Turno", "H. Inicio", "H. Cierre", "Apertura Neta", "Baño", "Refrigerio"]
                
                pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 8)
                for w, h in zip(cols_w3, headers3): pdf.cell(w, 5, h, border=1, fill=True, align='C')
                pdf.ln(); pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 8); pdf.set_draw_color(210, 210, 210)
                
                fill_row = False
                for _, fila in df_turnos.iterrows():
                    pdf.set_fill_color(248, 248, 248) if fill_row else pdf.set_fill_color(255, 255, 255)
                    maq_row = str(fila['MAQUINA']); turno_row = str(fila['TURNO'])
                    bano_mins = bano_dict.get((maq_row, turno_row), 0); refri_mins = refri_dict.get((maq_row, turno_row), 0)
                    str_bano = min_a_hhmm_hs(bano_mins) if bano_mins > 0 else "-"
                    str_refri = min_a_hhmm_hs(refri_mins) if refri_mins > 0 else "-"

                    pdf.cell(cols_w3[0], 4.5, maq_row, border=1, fill=True, align='L')
                    pdf.cell(cols_w3[1], 4.5, turno_row, border=1, fill=True, align='C')
                    pdf.cell(cols_w3[2], 4.5, str(fila['TXT_INICIO']), border=1, fill=True, align='C')
                    pdf.cell(cols_w3[3], 4.5, str(fila['TXT_CIERRE']), border=1, fill=True, align='C')
                    pdf.cell(cols_w3[4], 4.5, str(fila['TXT_APERTURA_NETA']), border=1, fill=True, align='C')
                    pdf.cell(cols_w3[5], 4.5, str_bano, border=1, fill=True, align='C')
                    pdf.cell(cols_w3[6], 4.5, str_refri, border=1, fill=True, align='C')
                    pdf.ln(); fill_row = not fill_row

            # --- SECCIÓN 4 ---
            pdf.ln(5)
            if pdf.get_y() > 260: pdf.add_page()
            pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
            pdf.set_link(link_resumen_grupo)
            pdf.cell(0, 6, txt="4. Resumen Tiempos Grupo", ln=True)
            pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(2)

            w_cat = 190 / 5
            pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 8.5)
            for titulo in ["Produccion", "Fallas/Gestion", "Paradas Prog.", "Proyecto", "Descansos"]: pdf.cell(w_cat, 5, titulo, border=1, fill=True, align='C')
            pdf.ln(); pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 8); pdf.set_draw_color(210, 210, 210); pdf.set_fill_color(255, 253, 208)
            for clave in ["Produccion", "Fallas/Gestion", "Paradas Prog.", "Proyecto", "Descansos"]: pdf.cell(w_cat, 5, min_a_hhmm_hs(tiempos_agrupados[clave]), border=1, fill=True, align='C')
            pdf.ln()

            # --- SECCIÓN 5 ---
            pdf.ln(6)
            if pdf.get_y() > 200: pdf.add_page()
            pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
            pdf.set_link(link_tendencias)
            pdf.cell(0, 6, txt="5. Análisis de Fallas y Tendencias", ln=True)
            pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(3)

            pdf.set_font("Arial", 'B', 10); pdf.set_text_color(211, 84, 0)
            y_actual = pdf.get_y()
            pdf.set_xy(10, y_actual); pdf.cell(90, 5, txt="> Top 15 Fallas:", ln=0)
            pdf.set_xy(105, y_actual); pdf.cell(90, 5, txt="> Tendencia Fallas:", ln=1)
            
            y_graficos = pdf.get_y()
            if os.path.exists('grafico_top_fallas.png'): pdf.image('grafico_top_fallas.png', x=10, y=y_graficos, w=92)
            if os.path.exists('grafico_tendencia.png'): pdf.image('grafico_tendencia.png', x=105, y=y_graficos, w=92)

            # --- SECCIÓN 6 ---
            pdf.set_y(y_graficos + 60); pdf.ln(4)
            if pdf.get_y() > 250: pdf.add_page()
            
            pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
            pdf.set_link(link_resumen_maq)
            pdf.cell(0, 6, txt="6. Cuadro Resumen por Máquinas", ln=True)
            pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(3)

            cols_w = [25, 23, 19, 23, 20, 80] 
            headers = ["MAQUINA", "PRODUCCION", "FALLAS", "PARADA PROG.", "DESCANSO", "TOP 3 FALLAS"]
            
            pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 6.5)
            for w, h in zip(cols_w, headers): pdf.cell(w, 5, h, border=1, fill=True, align='C')
            pdf.ln(); pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 6.5); pdf.set_draw_color(210, 210, 210)
            fill_row = False
            
            for m in sorted(list(resumen_maq_dict.keys())):
                if pdf.get_y() > 265:
                    pdf.add_page(); pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 6.5)
                    for w, h in zip(cols_w, headers): pdf.cell(w, 5, h, border=1, fill=True, align='C')
                    pdf.ln(); pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 6.5); pdf.set_draw_color(210, 210, 210)
                    
                pdf.set_fill_color(245, 248, 250) if fill_row else pdf.set_fill_color(255, 255, 255)
                
                prod = min_a_hhmm_hs(resumen_maq_dict[m].get('Produccion', 0)); fallas = min_a_hhmm_hs(resumen_maq_dict[m].get('Fallas', 0))
                parada = min_a_hhmm_hs(resumen_maq_dict[m].get('ParadaProg', 0)); descanso = min_a_hhmm_hs(resumen_maq_dict[m].get('Descanso', 0))
                top3_str = "\n".join(top3_dict.get(m, [])) if top3_dict.get(m, []) else "-"
                
                lines = len(top3_dict.get(m, [])) if len(top3_dict.get(m, [])) > 1 else 1
                line_height = 4.2; row_height = lines * line_height
                x_start, y_start = pdf.get_x(), pdf.get_y()
                
                pdf.cell(cols_w[0], row_height, m, border=1, fill=True, align='C')
                pdf.cell(cols_w[1], row_height, prod, border=1, fill=True, align='C')
                pdf.cell(cols_w[2], row_height, fallas, border=1, fill=True, align='C')
                pdf.cell(cols_w[3], row_height, parada, border=1, fill=True, align='C')
                pdf.cell(cols_w[4], row_height, descanso, border=1, fill=True, align='C')
                x_multi = pdf.get_x()
                pdf.multi_cell(cols_w[5], line_height, top3_str, border=1, fill=True, align='L')
                pdf.set_xy(x_start, y_start + row_height); fill_row = not fill_row

            # --- SECCIÓN 7 ---
            pdf.ln(6)
            if pdf.get_y() > 240: pdf.add_page() 
                
            pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
            pdf.set_link(link_dt_area)
            pdf.cell(0, 6, txt="7. Distribución de Down Time por Área", ln=True)
            pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(3)

            TARGETS_DT = {'MANTEN.': {'TRG': 1.0, 'MIN': 2.0, 'TRG_M': '4.5m', 'MIN_M': '9m'}, 'DISPOSIT.': {'TRG': 2.0, 'MIN': 3.5, 'TRG_M': '9m', 'MIN_M': '15.8m'}, 'TECNOL.': {'TRG': 2.0, 'MIN': 3.5, 'TRG_M': '9m', 'MIN_M': '15.8m'}, 'LOGIST.': {'TRG': 1.5, 'MIN': 2.5, 'TRG_M': '6.8m', 'MIN_M': '11.2m'}, 'GESTION': {'TRG': 1.5, 'MIN': 2.0, 'TRG_M': '6.8m', 'MIN_M': '9m'}, 'CALIDAD': {'TRG': 0.0, 'MIN': 0.0, 'TRG_M': '0m', 'MIN_M': '0m'}}
            cols_dt_w = [30, 26, 26, 26, 26, 26, 26]; headers_dt = ["MAQUINA", "MANTEN.", "DISPOSIT.", "TECNOL.", "LOGIST.", "GESTION", "CALIDAD"]
            
            pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 7)
            x_start, y_start = pdf.get_x(), pdf.get_y()
            pdf.multi_cell(cols_dt_w[0], 5, "MAQUINA\nTarget vs Real", border=1, fill=True, align='C') 
            
            for i, col_name in enumerate(headers_dt[1:]):
                x_col = x_start + cols_dt_w[0] + sum(cols_dt_w[1:i+1]); pdf.set_xy(x_col, y_start)
                txt_header = f"{col_name}\nTRG:{TARGETS_DT[col_name]['TRG']}% ({TARGETS_DT[col_name]['TRG_M']})\nMIN:{TARGETS_DT[col_name]['MIN']}% ({TARGETS_DT[col_name]['MIN_M']})"
                pdf.multi_cell(cols_dt_w[i+1], 3.3, txt_header, border=1, fill=True, align='C')
                    
            pdf.set_xy(10, y_start + 10); pdf.set_font("Arial", 'B', 8); pdf.set_draw_color(210, 210, 210)
            fill_row = False
            for m in sorted(list(areas_dt_dict.keys())):
                if pdf.get_y() > 265:
                    pdf.add_page(); pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 7)
                    x_start, y_start = pdf.get_x(), pdf.get_y()
                    pdf.multi_cell(cols_dt_w[0], 5, "MAQUINA\nTarget vs Real", border=1, fill=True, align='C') 
                    for i, col_name in enumerate(headers_dt[1:]):
                        x_col = x_start + cols_dt_w[0] + sum(cols_dt_w[1:i+1]); pdf.set_xy(x_col, y_start)
                        txt_header = f"{col_name}\nTRG:{TARGETS_DT[col_name]['TRG']}% ({TARGETS_DT[col_name]['TRG_M']})\nMIN:{TARGETS_DT[col_name]['MIN']}% ({TARGETS_DT[col_name]['MIN_M']})"
                        pdf.multi_cell(cols_dt_w[i+1], 3.3, txt_header, border=1, fill=True, align='C')
                    pdf.set_xy(10, y_start + 10); pdf.set_font("Arial", 'B', 8); pdf.set_draw_color(210, 210, 210)

                pdf.set_fill_color(245, 248, 250) if fill_row else pdf.set_fill_color(255, 255, 255)
                apertura_total = apertura_mensual_dict.get(m, 0)
                pdf.set_text_color(*COLOR_NEGRO); pdf.cell(cols_dt_w[0], 5.5, m, border=1, fill=True, align='C')
                
                for i, col_name in enumerate(headers_dt[1:]):
                    mins_area = areas_dt_dict[m].get(col_name, 0)
                    porcentaje = (mins_area / apertura_total * 100) if apertura_total > 0 else 0.0
                    trg, min_lim = TARGETS_DT[col_name]['TRG'], TARGETS_DT[col_name]['MIN']
                    
                    if porcentaje == 0.0: pdf.set_text_color(40, 167, 69)
                    elif porcentaje <= trg: pdf.set_text_color(40, 167, 69)
                    elif porcentaje >= min_lim: pdf.set_text_color(220, 53, 69)
                    else: pdf.set_text_color(230, 126, 34)
                    # Truncamos los decimales para coincidir con el sistema original
                    pdf.cell(cols_dt_w[i+1], 5.5, f"{porcentaje:.1f}% ({int(mins_area)}m)", border=1, fill=True, align='C')
                    
                pdf.ln(); fill_row = not fill_row

            # --- SECCIÓN 8 ---
            pdf.ln(6)
            if pdf.get_y() > 240: pdf.add_page()
            
            pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
            pdf.set_link(link_prod)
            pdf.cell(0, 6, txt="8. Desglose de Producción", ln=True)
            pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(3)

            if not df_top_prod.empty:
                maquinas_prod = df_top_prod['MAQUINA'].unique()
                for maq in sorted(maquinas_prod):
                    if pdf.get_y() > 250: pdf.add_page() 
                    df_maq_prod = df_top_prod[df_top_prod['MAQUINA'] == maq]
                    total_pzs = df_maq_prod['TOTAL_PRODUCIDO'].sum()
                    
                    pdf.set_font("Arial", 'B', 9); pdf.set_text_color(*COLOR_TITULO)
                    pdf.cell(0, 5, txt=f"Top 5 Códigos Producidos - {maq} (Total: {int(total_pzs)} pzs)", ln=True)
                    
                    cols_prod_w = [70, 24, 24, 24, 24, 24]
                    headers_prod = ["Codigo Producto", "Buenas", "Retrab.", "Observ.", "TC (Min)", "Pzs/h"]
                    pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 8)
                    for w, h in zip(cols_prod_w, headers_prod): pdf.cell(w, 5, h, border=1, fill=True, align='C')
                    pdf.ln()
                    
                    pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 7); pdf.set_draw_color(210, 210, 210)
                    fill_row = False
                    for _, row_prod in df_maq_prod.iterrows():
                        pdf.set_fill_color(245, 248, 250) if fill_row else pdf.set_fill_color(255, 255, 255)
                        
                        tc_val = float(row_prod['TC']) if not pd.isna(row_prod['TC']) else 0.0
                        if tc_val > 0:
                            tc_str = f"{tc_val:.1f}" if tc_val.is_integer() else str(round(tc_val, 3))
                            pzs_h = int(60 / tc_val)
                        else:
                            tc_str = "0.0"
                            pzs_h = 0

                        pdf.cell(cols_prod_w[0], 4.5, str(row_prod['CODIGO_PRODUCTO']), border=1, fill=True, align='C')
                        pdf.cell(cols_prod_w[1], 4.5, str(int(row_prod['BUENAS'])), border=1, fill=True, align='C')
                        pdf.cell(cols_prod_w[2], 4.5, str(int(row_prod['RETRABAJO'])), border=1, fill=True, align='C')
                        pdf.cell(cols_prod_w[3], 4.5, str(int(row_prod['OBSERVADAS'])), border=1, fill=True, align='C')
                        pdf.cell(cols_prod_w[4], 4.5, tc_str, border=1, fill=True, align='C')
                        pdf.cell(cols_prod_w[5], 4.5, str(pzs_h), border=1, fill=True, align='C')
                        pdf.ln(); fill_row = not fill_row
                    pdf.ln(3)

            # --- SECCIÓN 9: SECCIÓN FINAL (PERFORMANCE Y TIEMPOS) ---
            pdf.ln(6)
            if pdf.get_y() > 240: pdf.add_page()
            
            pdf.set_font("Arial", 'B', 14); pdf.set_text_color(*COLOR_TITULO)
            pdf.set_link(link_final)
            pdf.cell(0, 8, txt="SECCIÓN FINAL: PERFORMANCE Y TIEMPOS", ln=True)
            pdf.set_draw_color(210, 210, 210); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(6)

            if not df_perf_operarios.empty:
                pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
                pdf.cell(0, 6, txt="Performance de Operarios", ln=True)
                pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(2)

                cols_perf_w = [60, 45, 65, 20]
                headers_perf = ["Operador", "Fabrica", "Maquinas Operadas", "Perf."]
                
                pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 8)
                for w, h in zip(cols_perf_w, headers_perf): pdf.cell(w, 5, h, border=1, fill=True, align='C')
                pdf.ln()

                pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 8); pdf.set_draw_color(210, 210, 210)
                fill_row = False
                
                for _, row in df_perf_operarios.iterrows():
                    if pdf.get_y() > 270:
                        pdf.add_page()
                        pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 8)
                        for w, h in zip(cols_perf_w, headers_perf): pdf.cell(w, 5, h, border=1, fill=True, align='C')
                        pdf.ln(); pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 8); pdf.set_draw_color(210, 210, 210)
                        
                    pdf.set_fill_color(245, 248, 250) if fill_row else pdf.set_fill_color(255, 255, 255)
                    
                    perf_val = row['Perf']
                    perf_str = f"{perf_val:.0f}%" if not pd.isna(perf_val) else "0%"
                    
                    pdf.cell(cols_perf_w[0], 5, str(row['Operador'])[:35], border=1, fill=True, align='L')
                    pdf.cell(cols_perf_w[1], 5, str(row['Fabrica'])[:25], border=1, fill=True, align='C')
                    
                    maq_operadas = str(row['MaquinasOperadas'])
                    if pd.isna(row['MaquinasOperadas']) or row['MaquinasOperadas'] == 'None': maq_operadas = "-"
                    maq_operadas = maq_operadas.replace('CELDA ', 'Celda 0').replace('CEL', 'Celda ')
                    pdf.cell(cols_perf_w[2], 5, maq_operadas[:40], border=1, fill=True, align='C')
                    
                    if pd.notna(perf_val) and perf_val >= 100: pdf.set_text_color(40, 167, 69)
                    else: pdf.set_text_color(220, 53, 69)
                        
                    pdf.cell(cols_perf_w[3], 5, perf_str, border=1, fill=True, align='C')
                    pdf.set_text_color(*COLOR_NEGRO) 
                    pdf.ln(); fill_row = not fill_row
                pdf.ln(8)

            if not df_desc_operarios.empty:
                for tipo in ['BAÑO', 'REFRIGERIO']:
                    df_tipo = df_desc_operarios[df_desc_operarios['TipoDescanso'] == tipo]
                    if df_tipo.empty: continue

                    if pdf.get_y() > 250: pdf.add_page()
                    
                    pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
                    titulo_tabla = f"Tiempo de {tipo.capitalize()} Acumulado"
                    pdf.cell(0, 6, txt=titulo_tabla, ln=True)
                    pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(2)

                    cols_desc_w = [60, 50, 30, 25, 25]
                    headers_desc = ["Operador", "Fabrica", "Total Min", "Cant. Veces", "Promedio Min"]
                    
                    pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 8)
                    for w, h in zip(cols_desc_w, headers_desc): pdf.cell(w, 5, h, border=1, fill=True, align='C')
                    pdf.ln()

                    pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 8); pdf.set_draw_color(210, 210, 210)
                    fill_row = False
                    
                    for _, row in df_tipo.iterrows():
                        if pdf.get_y() > 270:
                            pdf.add_page()
                            pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 8)
                            for w, h in zip(cols_desc_w, headers_desc): pdf.cell(w, 5, h, border=1, fill=True, align='C')
                            pdf.ln(); pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 8); pdf.set_draw_color(210, 210, 210)
                            
                        pdf.set_fill_color(245, 248, 250) if fill_row else pdf.set_fill_color(255, 255, 255)
                        
                        pdf.cell(cols_desc_w[0], 5, str(row['Operador'])[:35], border=1, fill=True, align='L')
                        pdf.cell(cols_desc_w[1], 5, str(row['Fabrica'])[:25], border=1, fill=True, align='C')
                        
                        pdf.set_text_color(220, 53, 69) 
                        pdf.cell(cols_desc_w[2], 5, f"{row['TotalMin']:.1f}", border=1, fill=True, align='C')
                        
                        pdf.set_text_color(*COLOR_NEGRO) 
                        pdf.cell(cols_desc_w[3], 5, str(row['CantVeces']), border=1, fill=True, align='C')
                        
                        pdf.set_text_color(220, 53, 69) 
                        pdf.cell(cols_desc_w[4], 5, f"{row['PromedioMin']:.1f}", border=1, fill=True, align='C')
                        
                        pdf.set_text_color(*COLOR_NEGRO) 
                        pdf.ln(); fill_row = not fill_row
                    pdf.ln(8)

            # --- SECCIÓN 10: ANEXO ---
            if not df_horarios_diarios.empty:
                pdf.ln(4)
                if pdf.get_y() > 240: pdf.add_page()
                pdf.set_font("Arial", 'B', 12); pdf.set_text_color(*COLOR_TITULO)
                pdf.set_link(link_anexo)
                pdf.cell(0, 6, txt="10. Anexo: Registro Diario Exacto de Apertura y Cierre", ln=True)
                pdf.set_draw_color(*COLOR_TITULO); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(3)

                turnos_unicos = sorted(df_horarios_diarios['TURNO'].dropna().unique())
                cols_anexo_w = [25, 75, 45, 45]
                headers_anexo = ["FECHA", "MAQUINA", "HORA EXACTA INICIO", "HORA EXACTA FIN"]

                for turno in turnos_unicos:
                    if pdf.get_y() > 255: pdf.add_page()
                    pdf.set_font("Arial", 'B', 10); pdf.set_text_color(*COLOR_TITULO)
                    pdf.cell(0, 6, txt=f">> TABLA DEL TURNO {turno}", ln=True)
                    
                    pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(255, 255, 255); pdf.set_font("Arial", 'B', 8)
                    for w, h in zip(cols_anexo_w, headers_anexo): pdf.cell(w, 5, h, border=1, fill=True, align='C')
                    pdf.ln()

                    pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 7); pdf.set_draw_color(210, 210, 210)
                    df_turno = df_horarios_diarios[df_horarios_diarios['TURNO'] == turno].sort_values(by=['FECHA', 'MAQUINA'])
                    fill_row = False

                    for _, row in df_turno.iterrows():
                        if pdf.get_y() > 265:
                            pdf.add_page()
                            pdf.set_font("Arial", 'B', 9); pdf.set_text_color(*COLOR_TITULO)
                            pdf.cell(0, 6, txt=f">> TABLA DEL TURNO {turno} (Continuación)", ln=True)
                            pdf.set_fill_color(211, 84, 0); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 8)
                            for w, h in zip(cols_anexo_w, headers_anexo): pdf.cell(w, 5, h, border=1, fill=True, align='C')
                            pdf.ln(); pdf.set_text_color(*COLOR_NEGRO); pdf.set_font("Arial", '', 7); pdf.set_draw_color(210, 210, 210)

                        pdf.set_fill_color(245, 248, 250) if fill_row else pdf.set_fill_color(255, 255, 255)
                        fecha_str = row['FECHA'].strftime("%d/%m/%Y")
                        maq_str = formatear_nombre_maq(row['MAQUINA'])
                        hora_inicio_str = row['HORA_INICIO'].strftime("%H:%M:%S") if not pd.isna(row['HORA_INICIO']) else "Sin Registro"
                        hora_cierre_str = row['HORA_CIERRE'].strftime("%H:%M:%S") if not pd.isna(row['HORA_CIERRE']) else "Sin Registro"

                        pdf.cell(cols_anexo_w[0], 4.5, fecha_str, border=1, fill=True, align='C')
                        pdf.cell(cols_anexo_w[1], 4.5, maq_str, border=1, fill=True, align='L')
                        pdf.cell(cols_anexo_w[2], 4.5, hora_inicio_str, border=1, fill=True, align='C')
                        pdf.cell(cols_anexo_w[3], 4.5, hora_cierre_str, border=1, fill=True, align='C')
                        pdf.ln(); fill_row = not fill_row
                    pdf.ln(5) 

            nombre_pdf = f"Reporte_CELDA_RENAULT_{FECHA_INICIO}_al_{FECHA_FIN}.pdf"
            
            # Guardamos el PDF en el servidor
            pdf.output(nombre_pdf)
            
            # ---------------------------------------------------------
            # BOTÓN DE DESCARGA EN STREAMLIT
            # ---------------------------------------------------------
            st.success("✅ Procesamiento completado. El reporte está listo.")
            
            with open(nombre_pdf, "rb") as pdf_file:
                PDFbyte = pdf_file.read()

            st.download_button(
                label="📥 Descargar Reporte Gerencial (PDF)",
                data=PDFbyte,
                file_name=nombre_pdf,
                mime='application/octet-stream',
                use_container_width=True
            )

        except Exception as e:
            st.error(f"❌ Error crítico procesando la base de datos SQL. Detalle: {e}")

else:
    st.info("👈 Selecciona las fechas en el panel izquierdo y haz clic en 'Generar Reporte PDF'.")
