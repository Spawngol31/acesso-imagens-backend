# 📋 Contexto do Projeto Backend - Acesso Imagens

## 1. Visão Geral e Stack Tecnológica
* **Framework:** Python / Django / Django REST Framework (DRF).
* **Autenticação:** JWT (via `rest_framework_simplejwt`), Login Social (Google/Facebook).
* **Pagamentos:** Integração com Mercado Pago (Checkout transparente, Processamento e Webhooks).
* **Armazenamento de Mídia:** Upload direto (Direct-to-S3) via Presigned URLs, processamento de fila para fotos/vídeos.
* **Arquitetura de Roteamento:** O projeto utiliza um roteador central (`config/urls.py`) que mapeia todos os apps sob o prefixo global `/api/`.

## 2. Estrutura de Apps (Módulos)
* **`config`**: Configurações globais e roteador principal (`/api/` e `/admin/`).
* **`contas`**: Gestão de usuários, perfis, recuperação de senha, JWT e login social.
* **`core`**: Funcionalidades globais, utilitários, formulário de contato e ferramenta de marca d'água.
* **`galeria`**: Core de mídia. Lida com álbuns, busca facial, uploads, compartilhamento e avaliações.
* **`loja`**: Sistema financeiro e e-commerce. Gerencia carrinho, cupons, checkout (Mercado Pago), download/envio de mídia, propostas/negociações, dashboard financeiro dos fotógrafos e saques.
* **`perfis`**: Exibição pública dos fotógrafos ativos na plataforma.

## 3. Contrato de API (Principais Endpoints Disponíveis)
*Nota: Todos os endpoints abaixo já incluem o prefixo `/api/` mapeado no `config/urls.py`.*

### Autenticação e Usuários (`contas/`)
* `POST /api/token/` e `/api/token/refresh/` -> Autenticação JWT.
* `POST /api/registrar/` -> Cadastro de novos usuários.
* `GET/PUT /api/me/` -> Gerenciamento do próprio perfil.
* `POST /api/auth/google/` e `/api/auth/facebook/` -> Social Login.
* `POST /api/password-reset/` -> Recuperação de senha.

### Área Pública e Clientes (`galeria/`, `loja/`, `perfis/`)
* `GET /api/fotografos/` e `/api/fotografos-ativos/` -> Listagem pública de fotógrafos.
* `GET /api/albuns/` e `/api/albuns/<id>/` -> Visualização de álbuns.
* `POST /api/fotos/busca-facial/` -> Motor de reconhecimento facial.
* `GET /api/share/album/<pk>/` -> Preview de álbum compartilhado.
* `GET/POST /api/carrinho/` e `/api/carrinho/aplicar-cupom/` -> Gestão de compras.
* `POST /api/checkout/mp/process/` -> Processamento de pagamento via Mercado Pago.
* `GET /api/minhas-compras/` e `/api/minhas-propostas/` -> Área do cliente.

### Dashboard dos Fotógrafos (`galeria/`, `loja/`)
* `GET /api/dashboard/get-presigned-url/` -> Geração de link para upload S3.
* `POST /api/fotos/upload/` e `/api/dashboard/videos/upload/` -> Confirmação de mídia.
* `CRUD /api/dashboard/albuns/`, `/fotos/` e `/videos/` -> Gerenciamento de portfólio.
* `GET /api/dashboard/vendas/`, `/api/dashboard/minhas-vendas-json/` -> Relatórios financeiros.
* `GET /api/dashboard/propostas/` -> Gestão de negociações.
* `POST /api/dashboard/saques/` -> Solicitação de repasse financeiro.

### Dashboard Administrativo (`loja/`, `contas/`)
* `GET /api/admin/stats/` e `/api/admin/vendas-json/` -> Métricas gerais da plataforma.
* `GET /api/admin/users/` -> Gestão de usuários.
* `CRUD /api/admin/saques/` e `/api/admin/historico-pagamentos/` -> Repasses e fechamento.
* `GET /api/admin/exportar-pagamentos/` -> Exportação de logs para CSV.