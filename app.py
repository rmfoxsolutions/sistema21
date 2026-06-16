from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pmesp_sistema_2024_chave_segura')

_data_dir = '/data' if os.path.isdir('/data') else os.path.dirname(__file__)
DATABASE = os.path.join(_data_dir, 'sistema.db')


def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'usuario',
            nome TEXT NOT NULL,
            matricula TEXT,
            ativo INTEGER DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ocorrencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT UNIQUE NOT NULL,
            usuario_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            natureza TEXT,
            local_fato TEXT NOT NULL,
            bairro TEXT,
            descricao TEXT,
            status TEXT DEFAULT 'em_andamento',
            prioridade TEXT DEFAULT 'normal',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            encerrado_em TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS abordagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            nome_abordado TEXT NOT NULL,
            rg TEXT,
            cpf TEXT,
            local_abordagem TEXT NOT NULL,
            motivo TEXT NOT NULL,
            resultado TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            viatura TEXT,
            km_inicial INTEGER,
            km_final INTEGER,
            observacao TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        );
    ''')

    # Cria usuários padrão
    try:
        db.execute(
            'INSERT OR IGNORE INTO usuarios (username, senha, perfil, nome) VALUES (?, ?, ?, ?)',
            ('admin', generate_password_hash('admin'), 'admin', 'Administrador')
        )
        db.execute(
            'INSERT OR IGNORE INTO usuarios (username, senha, perfil, nome, matricula) VALUES (?, ?, ?, ?, ?)',
            ('teste', generate_password_hash('teste'), 'usuario', 'Viatura Teste', 'VTR-4500')
        )
        db.commit()
    except Exception as e:
        print(f'Erro ao criar usuários padrão: {e}')
    finally:
        db.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Por favor, faça login para continuar.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        if session.get('perfil') != 'admin':
            flash('Acesso restrito a administradores.', 'danger')
            return redirect(url_for('menu'))
        return f(*args, **kwargs)
    return decorated


def gerar_numero_ocorrencia(db):
    hoje = datetime.now().strftime('%Y%m%d')
    count = db.execute(
        'SELECT COUNT(*) FROM ocorrencias WHERE numero LIKE ?', (f'BO{hoje}%',)
    ).fetchone()[0]
    return f'BO{hoje}{count + 1:04d}'


# ─── Rotas ────────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return 'ok', 200


@app.route('/')
def index():
    if 'usuario_id' in session:
        if session.get('perfil') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('menu'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session:
        return redirect(url_for('index'))

    erro = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        senha = request.form.get('senha', '')

        db = get_db()
        usuario = db.execute(
            'SELECT * FROM usuarios WHERE username = ? AND ativo = 1', (username,)
        ).fetchone()
        db.close()

        if usuario and check_password_hash(usuario['senha'], senha):
            session.clear()
            session['usuario_id'] = usuario['id']
            session['username'] = usuario['username']
            session['nome'] = usuario['nome']
            session['perfil'] = usuario['perfil']
            session['matricula'] = usuario['matricula'] or ''

            if usuario['perfil'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('menu'))
        else:
            erro = 'Usuário ou senha inválidos.'

    return render_template('login.html', erro=erro)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/menu')
@login_required
def menu():
    db = get_db()
    total_ocorrencias = db.execute(
        'SELECT COUNT(*) FROM ocorrencias WHERE usuario_id = ?', (session['usuario_id'],)
    ).fetchone()[0]
    ultimas = db.execute(
        '''SELECT numero, tipo, local_fato, status, criado_em
           FROM ocorrencias WHERE usuario_id = ?
           ORDER BY criado_em DESC LIMIT 3''',
        (session['usuario_id'],)
    ).fetchall()
    db.close()
    return render_template('menu.html', total_ocorrencias=total_ocorrencias, ultimas=ultimas)


# ─── Ocorrência ───────────────────────────────────────────────────────────────

@app.route('/ocorrencia/nova', methods=['GET', 'POST'])
@login_required
def nova_ocorrencia():
    if request.method == 'POST':
        tipo = request.form.get('tipo', '').strip()
        natureza = request.form.get('natureza', '').strip()
        local_fato = request.form.get('local_fato', '').strip()
        bairro = request.form.get('bairro', '').strip()
        descricao = request.form.get('descricao', '').strip()
        prioridade = request.form.get('prioridade', 'normal')

        if not tipo or not local_fato:
            flash('Tipo e Local são obrigatórios.', 'danger')
            return render_template('ocorrencia_nova.html')

        db = get_db()
        numero = gerar_numero_ocorrencia(db)
        db.execute(
            '''INSERT INTO ocorrencias
               (numero, usuario_id, tipo, natureza, local_fato, bairro, descricao, prioridade)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (numero, session['usuario_id'], tipo, natureza, local_fato, bairro, descricao, prioridade)
        )
        db.commit()
        db.close()

        flash(f'Ocorrência {numero} registrada com sucesso!', 'success')
        return redirect(url_for('menu'))

    return render_template('ocorrencia_nova.html')


# ─── Abordagem ────────────────────────────────────────────────────────────────

@app.route('/abordagem/nova', methods=['GET', 'POST'])
@login_required
def nova_abordagem():
    if request.method == 'POST':
        nome_abordado = request.form.get('nome_abordado', '').strip()
        rg = request.form.get('rg', '').strip()
        cpf = request.form.get('cpf', '').strip()
        local_abordagem = request.form.get('local_abordagem', '').strip()
        motivo = request.form.get('motivo', '').strip()
        resultado = request.form.get('resultado', '').strip()

        if not nome_abordado or not local_abordagem or not motivo:
            flash('Nome, Local e Motivo são obrigatórios.', 'danger')
            return render_template('abordagem_nova.html')

        db = get_db()
        db.execute(
            '''INSERT INTO abordagens
               (usuario_id, nome_abordado, rg, cpf, local_abordagem, motivo, resultado)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (session['usuario_id'], nome_abordado, rg, cpf, local_abordagem, motivo, resultado)
        )
        db.commit()
        db.close()

        flash('Abordagem registrada com sucesso!', 'success')
        return redirect(url_for('menu'))

    return render_template('abordagem_nova.html')


# ─── Serviço ──────────────────────────────────────────────────────────────────

@app.route('/servico/inicio', methods=['GET', 'POST'])
@login_required
def inicio_servico():
    if request.method == 'POST':
        viatura = request.form.get('viatura', '').strip()
        km_inicial = request.form.get('km_inicial', '').strip()
        observacao = request.form.get('observacao', '').strip()

        db = get_db()
        db.execute(
            '''INSERT INTO servicos (usuario_id, tipo, viatura, km_inicial, observacao)
               VALUES (?, 'inicio', ?, ?, ?)''',
            (session['usuario_id'], viatura, km_inicial or None, observacao)
        )
        db.commit()
        db.close()

        flash('Início de serviço registrado!', 'success')
        return redirect(url_for('menu'))

    return render_template('servico_inicio.html')


@app.route('/servico/fim', methods=['GET', 'POST'])
@login_required
def fim_servico():
    if request.method == 'POST':
        viatura = request.form.get('viatura', '').strip()
        km_final = request.form.get('km_final', '').strip()
        observacao = request.form.get('observacao', '').strip()

        db = get_db()
        db.execute(
            '''INSERT INTO servicos (usuario_id, tipo, viatura, km_final, observacao)
               VALUES (?, 'fim', ?, ?, ?)''',
            (session['usuario_id'], viatura, km_final or None, observacao)
        )
        db.commit()
        db.close()

        flash('Fim de serviço registrado!', 'success')
        return redirect(url_for('menu'))

    return render_template('servico_fim.html')


# ─── Histórico do usuário ─────────────────────────────────────────────────────

@app.route('/historico')
@login_required
def historico():
    db = get_db()
    ocorrencias = db.execute(
        '''SELECT numero, tipo, natureza, local_fato, status, prioridade, criado_em
           FROM ocorrencias WHERE usuario_id = ?
           ORDER BY criado_em DESC LIMIT 20''',
        (session['usuario_id'],)
    ).fetchall()
    abordagens = db.execute(
        '''SELECT nome_abordado, local_abordagem, motivo, resultado, criado_em
           FROM abordagens WHERE usuario_id = ?
           ORDER BY criado_em DESC LIMIT 20''',
        (session['usuario_id'],)
    ).fetchall()
    db.close()
    return render_template('historico.html', ocorrencias=ocorrencias, abordagens=abordagens)


# ─── Admin ────────────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        'total_ocorrencias': db.execute('SELECT COUNT(*) FROM ocorrencias').fetchone()[0],
        'ocorrencias_hoje': db.execute(
            "SELECT COUNT(*) FROM ocorrencias WHERE date(criado_em) = date('now')"
        ).fetchone()[0],
        'total_abordagens': db.execute('SELECT COUNT(*) FROM abordagens').fetchone()[0],
        'abordagens_hoje': db.execute(
            "SELECT COUNT(*) FROM abordagens WHERE date(criado_em) = date('now')"
        ).fetchone()[0],
        'total_usuarios': db.execute("SELECT COUNT(*) FROM usuarios WHERE perfil = 'usuario'").fetchone()[0],
        'total_servicos': db.execute('SELECT COUNT(*) FROM servicos').fetchone()[0],
    }
    ultimas_ocorrencias = db.execute(
        '''SELECT o.numero, o.tipo, o.local_fato, o.status, o.prioridade,
                  o.criado_em, u.nome, u.matricula
           FROM ocorrencias o JOIN usuarios u ON o.usuario_id = u.id
           ORDER BY o.criado_em DESC LIMIT 10'''
    ).fetchall()
    ultimas_abordagens = db.execute(
        '''SELECT a.nome_abordado, a.local_abordagem, a.motivo, a.resultado,
                  a.criado_em, u.nome
           FROM abordagens a JOIN usuarios u ON a.usuario_id = u.id
           ORDER BY a.criado_em DESC LIMIT 10'''
    ).fetchall()
    db.close()
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        ultimas_ocorrencias=ultimas_ocorrencias,
        ultimas_abordagens=ultimas_abordagens
    )


if __name__ == '__main__':
    init_db()
    print('\n' + '='*50)
    print('  PMESP - Sistema Operacional')
    print('='*50)
    print('  Acesse: http://localhost:5000')
    print('  Admin:  admin / admin')
    print('  Teste:  teste / teste')
    print('='*50 + '\n')
    app.run(debug=True, host='0.0.0.0', port=5000)
