from flask import Flask, render_template, request, redirect, send_file, flash, session, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from controller.conexao import conectar
import pymysql
import os
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from wand.image import Image
from io import BytesIO

app = Flask(__name__, template_folder='templates')
app.secret_key = '1234'
login_manager = LoginManager(app)
login_manager.login_view = 'login'
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'upload')

class Usuario(UserMixin):
    def __init__(self, id, nome, senha, role):
        self.id = id
        self.nome = nome
        self.senha = senha
        self.role = role

    def get_id(self):
        return str(self.id)

class Pessoa:
    def __init__(self, id, nome, contrato, email, telefone, cpf):
        self.id = id
        self.nome = nome
        self.contrato = contrato
        self.email = email
        self.telefone = telefone
        self.cpf = cpf
        self.arquivos = []

    def add_arquivo(self, arquivo):
        self.arquivos.append(arquivo)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'contrato': self.contrato,
            'email': self.email,
            'telefone': self.telefone,
            'cpf': self.cpf,
            'arquivos': self.arquivos
        }


def verificar_credenciais(nome, senha):
    session['nome_usuario'] = nome
    try:
        con = conectar()
        cursor = con.cursor()

        query = "SELECT id, nome, senha, role FROM banco.usuarios WHERE nome = %s AND senha = %s"
        cursor.execute(query, (nome, senha))

        user = cursor.fetchone()

        cursor.close()
        con.close()

        if user:
            id, nome, senha, role = user    
            role = role.lower()
            return Usuario(id, nome, senha, role)
        return None

    except pymysql.Error as err:
        print("Erro: ", err)
        return None

def is_admin(user):
    return user.role == 'administrador' if user else False

@login_manager.user_loader
def load_user(user_id):
    try:
        con = conectar()
        cursor = con.cursor()

        query = "SELECT nome, senha FROM banco.usuarios WHERE id = %s"
        cursor.execute(query, (user_id,))
        user = cursor.fetchone()

        cursor.close()
        con.close()

        if user:
            nome, senha = user
            return verificar_credenciais(nome, senha)
        return None

    except pymysql.Error as err:
        print("Erro: ", err)
        return None
    

def gerar_miniatura_pdf(pdf_path):
    miniaturas = []
    with Image(filename=pdf_path, resolution=100) as img:
        img.format = 'jpg'
        for page in img.sequence:
            img_page = Image(page)
            miniaturas.append(img_page.make_blob('jpeg'))

    return miniaturas


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = verificar_credenciais(username, password)

        if user:
            login_user(user)
            return redirect('home')
        else:
            error = "Credenciais inválidas. Tente novamente"

    return render_template('login.html')

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        nome = request.form.get('name', '')
        contrato = request.form.get('contrato', '')
        email = request.form.get('email', '')
        telefone = request.form.get('number', '')
        cpf = request.form.get('cpf', '')
        arquivos = request.files.getlist('arquivo')

        criado_por = session['nome_usuario']

        conn = conectar()

        if conn:
            try:
                with conn.cursor() as cursor:
                    query = "INSERT INTO formulario (nome, contrato, email, telefone, cpf, criado_por) VALUES (%s, %s, %s, %s, %s, %s)"
                    cursor.execute(query, (nome, contrato, email, telefone, cpf, criado_por))
                    pessoa_id = cursor.lastrowid

                    for arquivo in arquivos:
                        if arquivo:
                            savepath = os.path.join(UPLOAD_FOLDER, secure_filename(arquivo.filename))
                            arquivo.save(savepath)

                            # Store the file in the 'arquivos' table
                            with open(savepath, 'rb') as file:
                                file_data = file.read()
                                insert_file_query = "INSERT INTO arquivos (arquivo, pessoa_id) VALUES (%s, %s)"
                                cursor.execute(insert_file_query, (file_data, pessoa_id))

                conn.commit()
            except pymysql.Error as error:
                print("Erro ao inserir os dados no banco de dados: ", error)
                conn.rollback()
            finally:
                conn.close()
        else:
            print("Não foi possível estabelecer a conexão com o banco de dados")

    return render_template('index.html')

@app.route('/cadastrar_user', methods=['GET', 'POST'])
def cadastrar_usuario():
    if request.method == 'POST':
        nome = request.form.get('nome', '')
        senha = request.form.get('senha', '')
        role = request.form.get('role', '')

        if verificar_usuario_existente(nome):
            flash("Usuário já existe. Escolha outro nome de usuário.", 'danger')
        else:
            conn = conectar()

            if conn:
                try:
                    with conn.cursor() as cursor:
                        criado_por = session.get('nome_usuario', '')  # Captura o nome do usuário logado
                        query = "INSERT INTO usuarios (nome, senha, role, criado_por) VALUES (%s, %s, %s, %s)"
                        cursor.execute(query, (nome, senha, role, criado_por))

                    conn.commit()
                    flash("Usuário cadastrado com sucesso.", 'success')
                    return redirect(('admin'))
                except pymysql.Error as error:
                    print("Erro ao inserir os dados no banco de dados: ", error)
                    conn.rollback()
                    flash("Erro ao cadastrar usuário. Tente novamente mais tarde.", 'danger')
                finally:
                    conn.close()
            else:
                flash("Não foi possível estabelecer a conexão com o banco de dados.", 'danger')

    return render_template('cadastrar_user.html')

def verificar_usuario_existente(nome):
    try:
        con = conectar()
        cursor = con.cursor()

        query = "SELECT id FROM usuarios WHERE nome = %s"
        cursor.execute(query, (nome,))

        user = cursor.fetchone()

        cursor.close()
        con.close()

        return user is not None

    except pymysql.Error as err:
        print("Erro: ", err)
        return False

@app.route('/admin')
@login_required
def admin():
    if not is_admin(current_user):
        return render_template('unauthorized.html')
    
    conn = conectar()
    try:
        cursor = conn.cursor()
        query = "Select id, nome, senha, role FROM usuarios"
        cursor.execute(query)
        resultados = cursor.fetchall()

        usuarios = []
        for resultado in resultados:
            id, nome, senha, role = resultado
            usuario = Usuario(id, nome, senha, role)
            usuarios.append(usuario)

        conn.commit()
        conn.close()
        cursor.close()

        return render_template('admin.html', usuarios=usuarios)
    except pymysql.Error as error:
        return "Erro ao obter a lista de usuarios no banco de dados:" + str(error)

@app.route('/pessoas')
def lista_pessoas():
    conn = conectar()
    try:
        cursor = conn.cursor()
        query = "SELECT id, nome, contrato, email, telefone, cpf FROM formulario"
        cursor.execute(query)
        resultados = cursor.fetchall()

        pessoas = []
        for resultado in resultados:
            pessoa = Pessoa(*resultado)

            # Fetch associated files for each person
            fetch_files_query = "SELECT arquivo FROM arquivos WHERE pessoa_id=%s"
            cursor.execute(fetch_files_query, (pessoa.id,))
            files = cursor.fetchall()
            for file_data in files:
                pessoa.add_arquivo(file_data[0])

            pessoas.append(pessoa)

        conn.commit()
        cursor.close()
        conn.close()

        return render_template('lista_pessoas.html', pessoas=pessoas)

    except pymysql.Error as error:
        return "Erro ao obter a lista de pessoas cadastradas no banco de dados: " + str(error)

@app.route('/editar/<string:tipo>/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(tipo, id):
    try:
        conn = conectar()
        cursor = conn.cursor()

        editado_por = session['nome_usuario']

        if tipo == 'usuario':
            query = "SELECT id, nome, senha, role FROM usuarios WHERE id=%s"
        elif tipo == 'pessoa':
            query = "SELECT id, nome, contrato, email, telefone, cpf, arquivo FROM formulario WHERE id=%s"
        else:
            return "Tipo de edição inválido."

        cursor.execute(query, (id,))
        resultado = cursor.fetchone()

        if resultado:
            if tipo == 'usuario':
                id, nome, senha, role = resultado
                item = {'id': id, 'nome': nome, 'senha': senha, 'role': role}

            elif tipo == 'pessoa':
                id, nome, contrato, email, telefone, cpf, arquivo = resultado
                item = {'id': id, 'nome': nome, 'contrato': contrato, 'email': email, 'telefone': telefone, 'cpf': cpf, 'arquivo': arquivo}

                if item['arquivo'] and item['arquivo'].endswith('.pdf'):
                    pdf_miniaturas = gerar_miniatura_pdf(os.path.join(UPLOAD_FOLDER, item['arquivo']))
                    item['pdf_miniaturas'] = pdf_miniaturas

            if request.method == 'POST':
                if 'excluir_arquivo' in request.form:
                    arquivo_path = os.path.join(UPLOAD_FOLDER, item['arquivo'])
                    if os.path.exists(arquivo_path):
                        os.remove(arquivo_path)

                    update_query = "UPDATE formulario SET arquivo=NULL WHERE id=%s"
                    cursor.execute(update_query, (id,))
                    conn.commit()

                    return redirect('/pessoas')

                if tipo == 'usuario':
                    novo_nome = request.form['nome']
                    nova_senha = request.form['senha']
                    novo_role = request.form['role']

                    update_query = "UPDATE usuarios SET nome=%s, senha=%s, role=%s, editado_por=%s WHERE id=%s"
                    cursor.execute(update_query, (novo_nome, nova_senha, novo_role, editado_por, id))
                elif tipo == 'pessoa':
                    novo_nome = request.form['nome']
                    novo_contrato = request.form['contrato']
                    novo_email = request.form['email']
                    novo_telefone = request.form['telefone']
                    novo_cpf = request.form['cpf']

                    update_query = "UPDATE formulario SET nome=%s, contrato=%s, email=%s, telefone=%s, cpf=%s, editado_por=%s WHERE id=%s"
                    cursor.execute(update_query, (novo_nome, novo_contrato, novo_email, novo_telefone, novo_cpf, editado_por, id))

                conn.commit()
                cursor.close()
                conn.close()

                return redirect('/pessoas' if tipo == 'pessoa' else '/admin')

            return render_template('editar.html', tipo=tipo, item=item, id=id)

    except pymysql.Error as error:
        print("Erro ao obter ou atualizar os dados do banco de dados: ", error)

    return redirect('/pessoas' if tipo == 'pessoa' else '/admin')

@app.route('/getFile/<filename>')
def getFile(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    return send_file(file_path, as_attachment=True)

@app.route('/excluir/<string:tipo>/<int:id>', methods=['POST'])
def excluir(tipo, id):
    if request.method == 'POST':
        try:
            conn = conectar()
            cursor = conn.cursor()

            if tipo == 'usuario':
                query = "DELETE FROM usuarios WHERE id=%s"
            elif tipo == 'pessoa':
                query = "DELETE FROM formulario WHERE id=%s"
            else:
                return "Tipo de exclusão inválido."

            cursor.execute(query, (id,))
            conn.commit()

            cursor.close()
            conn.close()

            return redirect('/pessoas' if tipo == 'pessoa' else '/admin')

        except pymysql.Error as error:
            print("Erro ao excluir os dados do banco de dados: ", error)

    return redirect('/pessoas' if tipo == 'pessoa' else '/admin')

@app.route('/excluir_arquivo/<int:id>', methods=['GET', 'POST'])
@login_required
def excluir_arquivo(id):
    if request.method == 'POST':
        try:
            conn = conectar()
            cursor = conn.cursor()

            # Primeiro, obtenha o nome do arquivo associado à pessoa com o ID fornecido
            query = "SELECT arquivo FROM formulario WHERE id=%s"
            cursor.execute(query, (id,))
            resultado = cursor.fetchone()

            if resultado and resultado[0]:
                # Remova o arquivo do sistema de arquivos
                arquivo_path = os.path.join(UPLOAD_FOLDER, resultado[0])
                if os.path.exists(arquivo_path):
                    os.remove(arquivo_path)

                # Atualize o registro no banco de dados para limpar o campo 'arquivo'
                update_query = "UPDATE formulario SET arquivo=NULL WHERE id=%s"
                cursor.execute(update_query, (id,))
                conn.commit()

                cursor.close()
                conn.close()

                flash("Arquivo excluído com sucesso.", 'success')
            else:
                flash("Nenhum arquivo associado a esta pessoa.", 'danger')

        except pymysql.Error as error:
            flash("Erro ao excluir o arquivo: " + str(error), 'danger')

    return redirect('/pessoas')

if __name__ == '__main__':
    app.run(debug=True)
