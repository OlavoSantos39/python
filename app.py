from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from passlib.context import CryptContext


# Configuração da Base de Dados SQLite
DATABASE_URL = "sqlite:///./barbearia.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Contexto para encriptar senhas com segurança
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# -------------------------------------------------------------
# Modelos da Base de Dados (Tabelas)
# -------------------------------------------------------------
class ClienteDB(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    telefone = Column(String, nullable=True)
    senha_hash = Column(String, nullable=False)

    agendamentos = relationship("AgendamentoDB", back_populates="cliente")


class BarbeariaDB(Base):
    __tablename__ = "barbearias"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    cnpj = Column(String, unique=True, nullable=False)
    telefone = Column(String, nullable=True)
    senha_hash = Column(String, nullable=False)


class AgendamentoDB(Base):
    __tablename__ = "agendamentos"
    id = Column(Integer, primary_key=True, index=True)
    data = Column(String, nullable=False)
    hora = Column(String, nullable=False)
    servico = Column(String, nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)

    cliente = relationship("ClienteDB", back_populates="agendamentos")


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------------
# Schemas Pydantic (Validação de Dados de Entrada)
# -------------------------------------------------------------
class ClienteCreate(BaseModel):
    nome: str
    email: EmailStr
    telefone: Optional[str] = None
    senha: str


class BarbeariaCreate(BaseModel):
    nome: str
    email: EmailStr
    cnpj: str
    telefone: Optional[str] = None
    senha: str


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str
    tipo: str  # "cliente" ou "barbearia"


class AgendamentoCreate(BaseModel):
    cliente_id: int
    data: str
    hora: str
    servico: str


# -------------------------------------------------------------
# Aplicação FastAPI
# -------------------------------------------------------------
app = FastAPI(title="Connect Barber Shop API")

# Configuração de CORS para permitir requisições do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Permite qualquer origem (ótimo para desenvolvimento local)
    allow_credentials=False,      # Alterado para False para evitar conflito com allow_origins=["*"]
    allow_methods=["*"],          # Permite todos os métodos (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],          # Permite todos os headers
)


# -------------------------------------------------------------
# Rotas da API
# -------------------------------------------------------------

@app.post("/api/cadastrar/cliente", status_code=status.HTTP_201_CREATED)
def cadastrar_cliente(dados: ClienteCreate, db: Session = Depends(get_db)):
    if db.query(ClienteDB).filter(ClienteDB.email == dados.email).first():
        raise HTTPException(status_code=400, detail="Este e-mail já está registado.")

    novo_cliente = ClienteDB(
        nome=dados.nome,
        email=dados.email,
        telefone=dados.telefone,
        senha_hash=pwd_context.hash(dados.senha)
    )
    db.add(novo_cliente)
    db.commit()
    db.refresh(novo_cliente)
    return {"mensagem": "Cliente registado com sucesso!", "id": novo_cliente.id}


@app.post("/api/cadastrar/barbearia", status_code=status.HTTP_201_CREATED)
def cadastrar_barbearia(dados: BarbeariaCreate, db: Session = Depends(get_db)):
    if db.query(BarbeariaDB).filter(BarbeariaDB.email == dados.email).first():
        raise HTTPException(status_code=400, detail="Este e-mail já está registado.")
    if db.query(BarbeariaDB).filter(BarbeariaDB.cnpj == dados.cnpj).first():
        raise HTTPException(status_code=400, detail="Este CNPJ já está registado.")

    nova_barbearia = BarbeariaDB(
        nome=dados.nome,
        email=dados.email,
        cnpj=dados.cnpj,
        telefone=dados.telefone,
        senha_hash=pwd_context.hash(dados.senha)
    )
    db.add(nova_barbearia)
    db.commit()
    db.refresh(nova_barbearia)
    return {"mensagem": "Barbearia registada com sucesso!", "id": nova_barbearia.id}


@app.post("/api/login")
def login(dados: LoginRequest, db: Session = Depends(get_db)):
    if dados.tipo == "cliente":
        usuario = db.query(ClienteDB).filter(ClienteDB.email == dados.email).first()
    elif dados.tipo == "barbearia":
        usuario = db.query(BarbeariaDB).filter(BarbeariaDB.email == dados.email).first()
    else:
        raise HTTPException(status_code=400, detail="Tipo de utilizador inválido.")

    if not usuario or not pwd_context.verify(dados.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    return {
        "status": "sucesso",
        "tipo": dados.tipo,
        "usuario": {
            "id": usuario.id,
            "nome": usuario.nome,
            "email": usuario.email
        }
    }


@app.post("/api/agendamentos", status_code=status.HTTP_201_CREATED)
def criar_agendamento(dados: AgendamentoCreate, db: Session = Depends(get_db)):
    cliente = db.query(ClienteDB).filter(ClienteDB.id == dados.cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    novo_agendamento = AgendamentoDB(
        cliente_id=dados.cliente_id,
        data=dados.data,
        hora=dados.hora,
        servico=dados.servico
    )
    db.add(novo_agendamento)
    db.commit()
    db.refresh(novo_agendamento)
    return {"mensagem": "Agendamento realizado com sucesso!", "id": novo_agendamento.id}


@app.get("/api/agendamentos/hoje")
def listar_agenda_hoje(db: Session = Depends(get_db)):
    data_hoje = datetime.today().strftime('%Y-%m-%d')
    agendamentos = db.query(AgendamentoDB).filter(AgendamentoDB.data == data_hoje).all()

    return [
        {
            "id": item.id,
            "hora": item.hora,
            "cliente": item.cliente.nome,
            "servico": item.servico
        } for item in agendamentos
    ]