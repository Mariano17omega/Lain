# Convergência do SCF

Plotado a partir de **um arquivo** de saída do `pw.x`. É o módulo de reserva: só vale quando nenhum outro tipo foi
detectado na pasta. Abre pelo **Plotar** no menu de contexto da saída ou pelo botão **Plotar SCF** da barra superior
(prévia, sem salvar).

Até três painéis empilhados, com o eixo de iterações compartilhado:

- **Precisão estimada** contra `conv_thr` (linha de limiar);
- **Energia**: |ΔE| entre iterações ou E total (**Energia como**); precisa de ≥ 2 iterações;
- **Magnetização** (apenas rodadas com spin).

Controles: **Escala** log/linear, mostrar cada painel e o limiar, janela de iterações (`xmin`/`xmax`), cores. Se o SCF
não convergiu, o gráfico diz "convergência NÃO atingida".

Código: `core/calculations/scf.py`.
