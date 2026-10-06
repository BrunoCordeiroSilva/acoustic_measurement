# Medição acústica

Interface Python/PySide6 para NI-9234. O ensaio de perda de transmissão (TL)
usa o método das duas cargas com **quatro microfones fixos**, em P1–P4.
Absorção sonora ainda não está implementada.

## Configuração e execução

Instale as dependências de `requirements.txt` em um ambiente virtual e o
driver NI-DAQmx no computador do laboratório. Execute `python main.py`.

Na aba Configuração, associe cada posição a um canal físico diferente e
informe a sensibilidade individual de cada microfone, conforme sua calibração.
A associação inicial é:

| Posição no tubo | Canal inicial | Função |
| --- | --- | --- |
| P1 | ai1 | Resposta H31 = P1/P3 |
| P2 | ai2 | Resposta H32 = P2/P3 |
| P3 | ai0 | Referência comum (preserva o canal do arranjo anterior) |
| P4 | ai3 | Resposta H34 = P4/P3 |

Os seletores permitem outra ordem de conexão: P3 continua sendo a referência
independentemente do número do canal. São necessários quatro microfones ativos
no mesmo módulo, sem canais ou posições duplicados. O fluxo antigo de microfone
móvel foi substituído; configurações de apenas dois canais não são aceitas em TL.
Mantenha todos os microfones nas mesmas posições durante o ensaio.

## Fluxo do ensaio

1. Configure canais, sensibilidades, geometria, médias e limites de coerência.
   Aplique a configuração e inicie o ensaio.
2. Instale a terminação A e clique em Medir. Cada média lê os quatro canais
   simultaneamente; H31, H32 e H34 usam exatamente o mesmo bloco adquirido.
3. Revise a qualidade e aceite a carga completa ou repita sua aquisição.
   Se houver avisos, a aceitação exige confirmação pelo operador.
4. Troque somente a terminação para B, confirme a troca e faça a segunda medição.
5. Aceite a carga B e clique em Processar TL.

Uma medição por terminação significa uma aquisição com o número de médias
configurado, não uma única média. Com apenas uma média, a coerência oficial não
é estatisticamente confiável e o sistema solicita revisão.

A aprovação exige qualidade nas três FRFs. O painel informa a menor coerência
média dos pares, a menor coerência da banda e a porcentagem de frequências que
atendem ao limite em todos os pares. Clipping é avaliado nos quatro canais.
A configuração fica bloqueada após adquirir uma carga, evitando misturar
parâmetros entre A e B. Refazer ensaio ou Novo ensaio/Modelo libera os campos.

Os gráficos exibem quatro espectros e três coerências identificados por posição.
Durante a medição oficial, são atualizados e ajustados (Zoom to fit) a cada média.
Depois, o espectro volta ao monitoramento e as coerências ficam congeladas na
última carga medida. O monitor preserva somente o último pacote e redesenha via
QTimer a cada 80 ms (no máximo 12,5 vezes/s), inclusive nos pop-ups.

## Resultados

A matriz ABCD e a TL continuam utilizando as seis FRFs: três da carga A e três
da B. A validade final intersecta as seis máscaras de coerência, a banda da
geometria e as verificações matemáticas/separação das cargas.

Salvar Ensaio CSV exporta `TL_<nome>_<numero>.csv`, os seis CSVs
`frf/H31_A.csv`, `H32_A.csv`, `H34_A.csv`, `H31_B.csv`,
`H32_B.csv`, `H34_B.csv` e `metadata.json`. Os metadados registram
o modo de quatro microfones fixos, suas posições e sensibilidades.
Arquivos antigos de FRF continuam legíveis pela opção de importar seis FRFs.
Importação/comparação de TL, visibilidade de curvas, PNG e CSV acumulado
permanecem disponíveis na aba Resultados.

Para outro modelo, salve o ensaio e use Novo ensaio/Modelo, atualizando
identificação e diretório sem precisar fechar o programa.

## Testes sem hardware

`python -B -m unittest discover -s tests -v`

A suíte usa uma DAQ simulada e Qt offscreen: verifica aquisição simultânea,
remapeamento dos canais, médias, qualidade, estados, cálculo de TL, exportação
e gráficos/pop-ups. O funcionamento elétrico, sincronismo e calibração dos
microfones devem ser conferidos no laboratório com a NI-9234.
