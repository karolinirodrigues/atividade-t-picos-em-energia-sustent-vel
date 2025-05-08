from flask import Flask, render_template, request, jsonify, send_file
import matplotlib.pyplot as plt
import io
import base64
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib
matplotlib.use('Agg')  # Necessary for environments without display
from fpdf import FPDF
import csv

app = Flask(__name__)

# Main route - displays the comparison form
@app.route('/')
def index():
    return render_template('index.html')

# Calculation endpoint - processes form data and returns comparison results
@app.route('/calcular', methods=['POST'])
def calcular():
    try:
        dados = request.get_json()
        
        # Validate required fields
        required_fields = ['tempo', 'km_ano', 'icev_preco', 'icev_consumo', 'icev_combustivel',
                          'icev_manutencao', 'icev_ipva', 'icev_seguro', 'ev_preco', 'ev_consumo',
                          'ev_energia', 'ev_manutencao', 'ev_ipva', 'ev_seguro']
        
        for field in required_fields:
            if field not in dados or not str(dados[field]).strip():
                return jsonify({'status': 'error', 'message': f'Campo obrigatório faltando: {field}'}), 400

        # Extract basic parameters
        tempo = int(dados['tempo'])
        km_ano = int(dados['km_ano'])
        inflacao = float(dados.get('inflacao', 5)) / 100
        var_combustivel = float(dados.get('variacao_combustivel', 7)) / 100
        var_energia = float(dados.get('variacao_energia', 3)) / 100

        # ICEV data
        icev = {
            'modelo': dados.get('icev_modelo', 'Personalizado'),
            'preco': float(dados['icev_preco']),
            'consumo': float(dados['icev_consumo']),
            'combustivel': float(dados['icev_combustivel']),
            'manutencao': float(dados['icev_manutencao']),
            'ipva': float(dados['icev_ipva']) / 100,
            'seguro': float(dados['icev_seguro'])
        }

        # EV data
        ev = {
            'modelo': dados.get('ev_modelo', 'Personalizado'),
            'preco': float(dados['ev_preco']),
            'consumo': float(dados['ev_consumo']),
            'energia': float(dados['ev_energia']),
            'manutencao': float(dados['ev_manutencao']),
            'ipva': float(dados['ev_ipva']) / 100,
            'seguro': float(dados['ev_seguro']),
            'bateria': float(dados.get('ev_bateria', 0)),
            'desconto_ipva': float(dados.get('ev_desconto_ipva', 0)) / 100
        }

        # ICEV calculations
        custo_combustivel_icev = sum(
            (km_ano / icev['consumo']) * icev['combustivel'] * (1 + var_combustivel)**ano 
            for ano in range(tempo)
        )
        
        custo_manutencao_icev = sum(
            icev['manutencao'] * (1 + inflacao)**ano 
            for ano in range(tempo)
        )
        
        custo_ipva_icev = sum(
            icev['preco'] * icev['ipva'] * max(0.1, (1 - 0.1*ano)) * (1 + inflacao)**ano
            for ano in range(tempo)
        )
        
        custo_seguro_icev = sum(
            icev['seguro'] * (1 + inflacao)**ano 
            for ano in range(tempo)
        )
        
        total_icev = icev['preco'] + custo_combustivel_icev + custo_manutencao_icev + custo_ipva_icev + custo_seguro_icev
        custo_km_icev = total_icev / (km_ano * tempo)

        # EV calculations
        custo_energia_ev = sum(
            (km_ano * ev['consumo']) * ev['energia'] * (1 + var_energia)**ano 
            for ano in range(tempo)
        )
        
        custo_manutencao_ev = sum(
            ev['manutencao'] * (1 + inflacao)**ano 
            for ano in range(tempo)
        )
        
        custo_ipva_ev = sum(
            ev['preco'] * ev['ipva'] * (1 - ev['desconto_ipva']) * max(0.1, (1 - 0.1*ano)) * (1 + inflacao)**ano
            for ano in range(tempo)
        )
        
        custo_seguro_ev = sum(
            ev['seguro'] * (1 + inflacao)**ano 
            for ano in range(tempo)
        )
        
        # Battery replacement every 8 years (if tempo > 8)
        custo_bateria_ev = sum(
            ev['bateria'] * (1 + inflacao)**(ano) 
            for ano in range(0, tempo, 8)
        ) if ev['bateria'] > 0 else 0
        
        total_ev = ev['preco'] + custo_energia_ev + custo_manutencao_ev + custo_ipva_ev + custo_seguro_ev + custo_bateria_ev
        custo_km_ev = total_ev / (km_ano * tempo)

        # Determine best option
        melhor_opcao = 'EV' if total_ev < total_icev else 'ICEV'
        economia = abs(total_icev - total_ev)

        # Generate comparative graph
        anos = list(range(1, tempo + 1))
        
        # Yearly accumulated calculations
        acumulado_icev = []
        acumulado_ev = []
        
        for ano in anos:
            # ICEV
            c_comb = sum((km_ano / icev['consumo']) * icev['combustivel'] * (1 + var_combustivel)**a for a in range(ano))
            c_man = sum(icev['manutencao'] * (1 + inflacao)**a for a in range(ano))
            c_ipva = sum(icev['preco'] * icev['ipva'] * max(0.1, (1 - 0.1*a)) * (1 + inflacao)**a for a in range(ano))
            c_seg = sum(icev['seguro'] * (1 + inflacao)**a for a in range(ano))
            acumulado_icev.append(icev['preco'] + c_comb + c_man + c_ipva + c_seg)
            
            # EV
            c_ener = sum((km_ano * ev['consumo']) * ev['energia'] * (1 + var_energia)**a for a in range(ano))
            c_man_ev = sum(ev['manutencao'] * (1 + inflacao)**a for a in range(ano))
            c_ipva_ev = sum(ev['preco'] * ev['ipva'] * (1 - ev['desconto_ipva']) * max(0.1, (1 - 0.1*a)) * (1 + inflacao)**a for a in range(ano))
            c_seg_ev = sum(ev['seguro'] * (1 + inflacao)**a for a in range(ano))
            c_bat = sum(ev['bateria'] * (1 + inflacao)**(a) for a in range(0, ano, 8)) if ev['bateria'] > 0 else 0
            acumulado_ev.append(ev['preco'] + c_ener + c_man_ev + c_ipva_ev + c_seg_ev + c_bat)

        # Create graph
        plt.figure(figsize=(10, 6))
        plt.plot(anos, acumulado_icev, label='ICEV', color='#FF6B6B', linewidth=2)
        plt.plot(anos, acumulado_ev, label='EV', color='#4ECDC4', linewidth=2)
        plt.fill_between(anos, acumulado_icev, acumulado_ev, where=[a > b for a, b in zip(acumulado_ev, acumulado_icev)], 
                        color='#4ECDC4', alpha=0.2, interpolate=True)
        plt.fill_between(anos, acumulado_icev, acumulado_ev, where=[a <= b for a, b in zip(acumulado_ev, acumulado_icev)], 
                        color='#FF6B6B', alpha=0.2, interpolate=True)
        
        plt.title('Comparação de Custos ao Longo do Tempo', pad=20)
        plt.xlabel('Anos')
        plt.ylabel('Custo Acumulado (R$)')
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # Save graph to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
        buffer.seek(0)
        grafico_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        plt.close()

        # Prepare response
        resultados = {
            'status': 'success',
            'resultados': {
                'tempo': tempo,
                'km_ano': km_ano,
                'total_icev': round(total_icev, 2),
                'total_ev': round(total_ev, 2),
                'custo_km_icev': round(custo_km_icev, 4),
                'custo_km_ev': round(custo_km_ev, 4),
                'melhor_opcao': melhor_opcao,
                'economia': round(economia, 2),
                'grafico_url': grafico_base64,
                'detalhes': {
                    'icev': icev,
                    'ev': ev,
                    'parametros': {
                        'inflacao': inflacao,
                        'var_combustivel': var_combustivel,
                        'var_energia': var_energia
                    }
                }
            }
        }

        return jsonify(resultados)

    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'Valor inválido: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Erro no cálculo: {str(e)}'}), 500

# Export endpoints
@app.route('/exportar/<tipo>', methods=['POST'])
def exportar(tipo):
    try:
        dados = request.get_json()
        
        if tipo not in ['pdf', 'csv']:
            return jsonify({'status': 'error', 'message': 'Tipo de exportação inválido'}), 400
            
        if tipo == 'pdf':
            return exportar_pdf(dados)
        else:
            return exportar_csv(dados)
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def exportar_pdf(dados):
    """Generate PDF report with comparison results"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Comparação VE vs ICEV", ln=1, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=1, align='C')
    pdf.ln(10)
    
    # Parameters
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Parâmetros da Análise", ln=1)
    pdf.set_font("Arial", size=12)
    
    pdf.cell(100, 10, txt=f"Tempo de propriedade: {dados['tempo']} anos", ln=1)
    pdf.cell(100, 10, txt=f"Quilometragem anual: {dados['km_ano']} km", ln=1)
    pdf.ln(5)
    
    # Results
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Resultados", ln=1)
    pdf.set_font("Arial", size=12)
    
    pdf.cell(100, 10, txt=f"TCO Total ICEV: R$ {dados['total_icev']:,.2f}", ln=1)
    pdf.cell(100, 10, txt=f"TCO Total EV: R$ {dados['total_ev']:,.2f}", ln=1)
    pdf.cell(100, 10, txt=f"Custo por km ICEV: R$ {dados['custo_km_icev']:,.4f}", ln=1)
    pdf.cell(100, 10, txt=f"Custo por km EV: R$ {dados['custo_km_ev']:,.4f}", ln=1)
    pdf.ln(5)
    
    melhor = "VE (Elétrico)" if dados['melhor_opcao'] == 'EV' else "ICEV (Combustão)"
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=f"Melhor opção: {melhor}", ln=1)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Economia em {dados['tempo']} anos: R$ {dados['economia']:,.2f}", ln=1)
    
    # Save PDF to buffer
    buffer = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    buffer.write(pdf_bytes)
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"comparacao_veiculos_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
        mimetype='application/pdf'
    )

def exportar_csv(dados):
    """Generate CSV report with comparison results"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';')
    
    # Header
    writer.writerow(["Comparação VE vs ICEV"])
    writer.writerow([f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}"])
    writer.writerow([])
    
    # Parameters
    writer.writerow(["Parâmetros da Análise"])
    writer.writerow(["Tempo de propriedade (anos)", dados['tempo']])
    writer.writerow(["Quilometragem anual (km)", dados['km_ano']])
    writer.writerow([])
    
    # Results
    writer.writerow(["Resultados"])
    writer.writerow(["TCO Total ICEV (R$)", f"{dados['total_icev']:,.2f}"])
    writer.writerow(["TCO Total EV (R$)", f"{dados['total_ev']:,.2f}"])
    writer.writerow(["Custo por km ICEV (R$/km)", f"{dados['custo_km_icev']:,.4f}"])
    writer.writerow(["Custo por km EV (R$/km)", f"{dados['custo_km_ev']:,.4f}"])
    writer.writerow([])
    
    melhor = "VE (Elétrico)" if dados['melhor_opcao'] == 'EV' else "ICEV (Combustão)"
    writer.writerow(["Melhor opção", melhor])
    writer.writerow([f"Economia em {dados['tempo']} anos (R$)", f"{dados['economia']:,.2f}"])
    
    buffer.seek(0)
    return send_file(
        io.BytesIO(buffer.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name=f"comparacao_veiculos_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mimetype='text/csv'
    )

if __name__ == '__main__':
    app.run(debug=True)