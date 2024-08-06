from flask import Flask, render_template, request, redirect, url_for, session
import pymysql
import re
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secreto'

db = pymysql.connect(host='database-aws.cd0404mis0qo.us-east-2.rds.amazonaws.com',
                     user='admin',
                     password='Fnlj1984AWS',
                     database='bancolab',
                     cursorclass=pymysql.cursors.DictCursor)

def remove_mascara_cpf(cpf):
    return re.sub(r'\D', '', cpf)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        cpf = remove_mascara_cpf(request.form['cpf'])
        senha = request.form['senha']
        cursor = db.cursor()
        cursor.execute('SELECT * FROM usuarios WHERE cpf = %s AND senha = %s', (cpf, senha))
        usuario = cursor.fetchone()
        if usuario:
            session['usuario_id'] = usuario['id']
            session['nome'] = usuario['nome']
            if cpf in ['04976675416', '04957913420']:
                return redirect(url_for('admin'))
            return redirect(url_for('bem_vindo'))
        else:
            return 'Credenciais inválidas. <a href="/login">Tente novamente.</a>'
    return render_template('login.html')


@app.route('/admin')
def admin():
    if 'usuario_id' in session:
        cursor = db.cursor()
        cursor.execute('''
            SELECT id, cpf, nome
            FROM usuarios
            WHERE cpf NOT IN ('04976675416', '04957913420')
        ''')
        usuarios = cursor.fetchall()
        return render_template('admin.html', usuarios=usuarios)
    return redirect(url_for('login'))


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        cpf = remove_mascara_cpf(request.form['cpf'])
        nome = request.form['nome']
        senha = request.form['senha']
        cursor = db.cursor()
        try:
            cursor.execute('INSERT INTO usuarios (cpf, nome, senha) VALUES (%s, %s, %s)', (cpf, nome, senha))
            db.commit()
            return 'Usuário cadastrado com sucesso. <a href="/login">Faça login.</a>'
        except pymysql.err.IntegrityError:
            return 'CPF já cadastrado. <a href="/cadastro">Tente novamente.</a>'
    return render_template('cadastro.html')

@app.route('/bem-vindo', methods=['GET', 'POST'])
def bem_vindo():
    if 'usuario_id' in session:
        usuario_id = session['usuario_id']
        cursor = db.cursor()
        
        # Verifica se já existe registro de entrada para o usuário no dia atual
        cursor.execute('SELECT * FROM registros WHERE usuario_id = %s AND DATE(data_hora) = CURDATE() AND tipo = %s', (usuario_id, 'entrada'))
        registro_entrada = cursor.fetchone()
        
        # Verifica se já existe registro de saída para o usuário no dia atual
        cursor.execute('SELECT * FROM registros WHERE usuario_id = %s AND DATE(data_hora) = CURDATE() AND tipo = %s', (usuario_id, 'saida'))
        registro_saida = cursor.fetchone()
        
        # Se houver registro de saída, busca as atividades do dia associadas a esse registro
        if registro_saida:
            cursor.execute('SELECT observacao FROM registros WHERE usuario_id = %s AND DATE(data_hora) = CURDATE() AND tipo = %s', (usuario_id, 'saida'))
            atividades_do_dia = cursor.fetchone()['observacao']
        else:
            atividades_do_dia = ''
        
        return render_template('bemvindo.html', nome=session['nome'], registro_entrada=registro_entrada, registro_saida=registro_saida, atividades_do_dia=atividades_do_dia)
    
    return redirect(url_for('login'))

@app.route('/registrar_entrada', methods=['POST'])
def registrar_entrada():
    if 'usuario_id' in session:
        usuario_id = session['usuario_id']
        agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = db.cursor()
        try:
            cursor.execute('INSERT INTO registros (usuario_id, tipo, data_hora) VALUES (%s, %s, %s)', (usuario_id, 'entrada', agora))
            db.commit()
            return redirect(url_for('bem_vindo'))
        except Exception as e:
            db.rollback()
            return f'Erro ao registrar entrada: {str(e)}'
    else:
        return redirect(url_for('login'))

@app.route('/registrar_saida', methods=['POST'])
def registrar_saida():
    if 'usuario_id' in session:
        usuario_id = session['usuario_id']
        agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        atividades_do_dia = request.form.get('atividades', '')
        cursor = db.cursor()
        try:
            cursor.execute('INSERT INTO registros (usuario_id, tipo, data_hora, observacao) VALUES (%s, %s, %s, %s)', (usuario_id, 'saida', agora, atividades_do_dia))
            db.commit()
            return redirect(url_for('bem_vindo'))
        except Exception as e:
            db.rollback()
            return f'Erro ao registrar saída: {str(e)}'
    else:
        return redirect(url_for('login'))
    
@app.route('/relatorio', methods=['GET'])
def relatorio():
    if 'usuario_id' in session:
        usuario_id = request.args.get('usuario_id', session['usuario_id'])
        cursor = db.cursor()

        # Obter parâmetros de filtro
        mes = request.args.get('mes', None)
        ano = request.args.get('ano', None)
        exibir_todos_dias = request.args.get('exibir_todos_dias', 'false') == 'true'
        pagina = int(request.args.get('pagina', 1))
        por_pagina = int(request.args.get('por_pagina', 20))
        ordenacao = request.args.get('ordenacao', 'desc')

        # Obter a data do primeiro e do último registro do usuário
        cursor.execute('''
            SELECT MIN(DATE(data_hora)) as primeira_data, MAX(DATE(data_hora)) as ultima_data
            FROM registros
            WHERE usuario_id = %s
        ''', (usuario_id,))
        data_range = cursor.fetchone()
        primeira_data = data_range['primeira_data']
        ultima_data = data_range['ultima_data']

        # Construir a consulta SQL com base no filtro
        query = '''
            SELECT 
                DATE(data_hora) as data,
                MIN(CASE WHEN tipo = 'entrada' THEN data_hora END) as hora_entrada,
                MAX(CASE WHEN tipo = 'saida' THEN data_hora END) as hora_saida,
                MAX(CASE WHEN tipo = 'saida' THEN observacao END) as observacao
            FROM registros 
            WHERE usuario_id = %s
        '''
        params = [usuario_id]

        if mes and ano:
            query += ' AND MONTH(data_hora) = %s AND YEAR(data_hora) = %s'
            params.extend([mes, ano])
        elif mes:
            query += ' AND MONTH(data_hora) = %s'
            params.append(mes)
        elif ano:
            query += ' AND YEAR(data_hora) = %s'
            params.append(ano)

        query += ' GROUP BY DATE(data_hora) ORDER BY DATE(data_hora) ' + ordenacao
        query += ' LIMIT %s OFFSET %s'
        params.extend([por_pagina, (pagina - 1) * por_pagina])

        cursor.execute(query, params)
        registros = cursor.fetchall()

        # Calcular o total de registros para a paginação
        cursor.execute('''
            SELECT COUNT(DISTINCT DATE(data_hora)) as total
            FROM registros
            WHERE usuario_id = %s
        ''', (usuario_id,))
        total_registros = cursor.fetchone()['total']
        total_paginas = (total_registros + por_pagina - 1) // por_pagina

        # Preencher dias sem registros se exibir_todos_dias for True
        if exibir_todos_dias and primeira_data and ultima_data:
            from datetime import datetime, timedelta

            # Cria um dicionário com os dias do intervalo como chaves e registros como valores
            delta = (ultima_data - primeira_data).days + 1
            todos_registros = {primeira_data + timedelta(days=i): {'data': primeira_data + timedelta(days=i), 'hora_entrada': None, 'hora_saida': None, 'observacao': '', 'intervalo': 0} for i in range(delta)}

            # Atualiza o dicionário com os registros reais
            for registro in registros:
                data = registro['data']
                todos_registros[data].update(registro)
            
            # Converte o dicionário de volta para uma lista de registros
            registros = list(todos_registros.values())

        total_tempo_trabalhado = 0
        for registro in registros:
            if registro['hora_entrada'] and registro['hora_saida']:
                entrada = registro['hora_entrada']
                saida = registro['hora_saida']
                intervalo = (saida - entrada).total_seconds()
                registro['intervalo'] = intervalo
                total_tempo_trabalhado += intervalo
            else:
                registro['intervalo'] = 0

        total_horas, remainder = divmod(total_tempo_trabalhado, 3600)
        total_minutos, _ = divmod(remainder, 60)

        return render_template('relatorio.html', nome=session['nome'], registros=registros, mes=mes, ano=ano, total_horas=int(total_horas), total_minutos=int(total_minutos), pagina=pagina, total_paginas=total_paginas, por_pagina=por_pagina, ordenacao=ordenacao, exibir_todos_dias=exibir_todos_dias)
    
    return redirect(url_for('login'))

@app.route('/relatorio_admin', methods=['GET'])
def relatorio_admin():
    if 'usuario_id' in session:
        admin_id = session['usuario_id']
        usuario_id = request.args.get('usuario_id')
        cursor = db.cursor()

        # Obter nome do usuário
        cursor.execute('SELECT nome FROM usuarios WHERE id = %s', (usuario_id,))
        nome_usuario = cursor.fetchone()['nome']

        # Obter parâmetros de filtro
        mes = request.args.get('mes', None)
        ano = request.args.get('ano', None)
        exibir_todos_dias = request.args.get('exibir_todos_dias', 'false') == 'true'

        # Obter parâmetros de paginação
        pagina = int(request.args.get('pagina', 1))
        por_pagina = int(request.args.get('por_pagina', 20))

        # Obter parâmetro de ordenação
        ordenacao = request.args.get('ordenacao', 'desc')

        # Obter a data do primeiro e do último registro do usuário
        cursor.execute('''
            SELECT MIN(DATE(data_hora)) as primeira_data, MAX(DATE(data_hora)) as ultima_data
            FROM registros
            WHERE usuario_id = %s
        ''', (usuario_id,))
        data_range = cursor.fetchone()
        primeira_data = data_range['primeira_data']
        ultima_data = data_range['ultima_data']

        # Construir a consulta SQL com base no filtro e ordenação
        query = '''
            SELECT 
                DATE(data_hora) as data,
                MIN(CASE WHEN tipo = 'entrada' THEN data_hora END) as hora_entrada,
                MAX(CASE WHEN tipo = 'saida' THEN data_hora END) as hora_saida,
                MAX(CASE WHEN tipo = 'saida' THEN observacao END) as observacao
            FROM registros 
            WHERE usuario_id = %s
        '''
        params = [usuario_id]

        if mes and ano:
            query += ' AND MONTH(data_hora) = %s AND YEAR(data_hora) = %s'
            params.extend([mes, ano])
        elif mes:
            query += ' AND MONTH(data_hora) = %s'
            params.append(mes)
        elif ano:
            query += ' AND YEAR(data_hora) = %s'
            params.append(ano)

        query += ' GROUP BY DATE(data_hora) ORDER BY DATE(data_hora) ' + ordenacao.upper()
        query += ' LIMIT %s OFFSET %s'
        params.extend([por_pagina, (pagina - 1) * por_pagina])

        cursor.execute(query, params)
        registros = cursor.fetchall()

        # Calcular o total de registros para a paginação
        cursor.execute('''
            SELECT COUNT(DISTINCT DATE(data_hora)) as total
            FROM registros
            WHERE usuario_id = %s
        ''', (usuario_id,))
        total_registros = cursor.fetchone()['total']
        total_paginas = (total_registros + por_pagina - 1) // por_pagina

        # Preencher dias sem registros se exibir_todos_dias for True
        if exibir_todos_dias and primeira_data and ultima_data:
            from datetime import datetime, timedelta

            # Cria um dicionário com os dias do intervalo como chaves e registros como valores
            delta = (ultima_data - primeira_data).days + 1
            todos_registros = {primeira_data + timedelta(days=i): {'data': primeira_data + timedelta(days=i), 'hora_entrada': None, 'hora_saida': None, 'observacao': '', 'intervalo': 0} for i in range(delta)}

            # Atualiza o dicionário com os registros reais
            for registro in registros:
                data = registro['data']
                todos_registros[data].update(registro)
            
            # Converte o dicionário de volta para uma lista de registros
            registros = list(todos_registros.values())

        total_tempo_trabalhado = 0
        for registro in registros:
            if registro['hora_entrada'] and registro['hora_saida']:
                entrada = registro['hora_entrada']
                saida = registro['hora_saida']
                intervalo = (saida - entrada).total_seconds()
                registro['intervalo'] = intervalo
                total_tempo_trabalhado += intervalo
            else:
                registro['intervalo'] = 0

        total_horas, remainder = divmod(total_tempo_trabalhado, 3600)
        total_minutos, _ = divmod(remainder, 60)

        return render_template('relatorio_admin.html', nome_usuario=nome_usuario, registros=registros, mes=mes, ano=ano, total_horas=int(total_horas), total_minutos=int(total_minutos), pagina=pagina, total_paginas=total_paginas, por_pagina=por_pagina, ordenacao=ordenacao, usuario_id=usuario_id, exibir_todos_dias=exibir_todos_dias)
    
    return redirect(url_for('login'))





if __name__ == '__main__':
    app.run(debug=True)
