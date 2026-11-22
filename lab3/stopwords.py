FR = set("""
a à au aux avec ce ces cet cette ceci cela ça celui celle celles ceux chaque comme dans de des du
elle elles en entre et eux il ils je la le les leur leurs lui ma mais me même mêmes mes moi mon ne
ni nos notre nous on ou où par pas pour qu que qui quoi sa sans se ses si son sous sur ta te tes
toi ton tu un une unes uns vos votre vous y d l j m n s t c qu jusqu lorsqu puisqu quelqu
été étée étées étés étant suis es est sommes êtes sont serai seras sera serons serez seront serais
serait serions seriez seraient étais était étions étiez étaient fus fut fûmes fûtes furent sois soit
soyons soyez soient fusse fût ai as avons avez ont aurai auras aura aurons aurez auront aurais aurait
aurions auriez auraient avais avait avions aviez avaient eut eurent eu ayant avoir être fait faire
font peut peuvent pouvait doit doivent devient deviennent sans plus moins très trop peu bien aussi
alors ainsi donc car puis encore déjà toujours jamais souvent parfois ici là dont lequel laquelle
lesquels lesquelles auquel auxquels duquel desquels tout tous toute toutes autre autres aucun aucune
certains certaines plusieurs quelque quelques tel telle tels telles tant autant afin depuis pendant
avant après chez contre vers selon parmi lors outre via cependant néanmoins toutefois pourtant
enfin ensuite également notamment surtout seulement non oui leurs celui-ci celle-ci ceux-ci
quand comment pourquoi combien chacun chacune rien personne quoi soi d'autant ailleurs dès
part fois sorte manière façon cas exemple ainsi lors cours point
lorsque puisque quoique tandis parce celui-là voici voilà
deux trois quatre cinq six sept huit neuf dix onze douze vingt trente cent cents mille premier première second seconde
""".split())

IT = set("""
a ad al allo alla ai agli alle all anche avere ben che chi ci con col coi contro cui da dal dallo
dalla dai dagli dalle dall del dello della dei degli delle dell di dove e ed era erano essere fra
gli ha hanno ho i il in io la le lei li lo loro lui ma me mi mia mie miei mio ne negli nei nel nella
nelle nello nell noi non nostra nostre nostri nostro o od per perché più poi qual quale quali quando
quanto quella quelle quelli quello questa queste questi questo se sei si sia siamo siete sono sta su
sua sue sui sul sulla sulle sullo sull suo suoi ti tra tu tua tue tuo tuoi tutti tutto tutta tutte
un una uno vi voi c l d s m t un' quell nell' dell' all' sull' dall' anch'
è sei siamo siete fu furono fosse fossero sarà saranno sarebbe sarebbero stato stata stati state
essendo abbiamo avete avevano aveva avevo avuto avendo abbia abbiano ebbe ebbero avrà avrebbe
può possono poteva potrebbe deve devono viene vengono venne fa fanno fatto fare
molto molti molta molte poco pochi tanto tanti troppo sempre già ancora mai spesso anche inoltre
quindi dunque però invece mentre come così cioè ovvero oppure infatti pure soltanto solo proprio
altro altri altra altre ogni ognuno ciascuno ciascuna nessuno nessuna qualche alcuni alcune alcuno
stesso stessa stessi stesse tale tali tra fra verso dopo prima durante senza secondo presso circa
oltre attraverso mediante grazie modo volta volte esempio caso parte tipo cosa cose qui là lì
dove ove sebbene benché affinché poiché perciò comunque tuttavia ossia nonché ecco essa esse esso
essi egli ella costoro colui colei coloro ciò questo quel quei quegli
due tre quattro cinque sei sette otto nove dieci undici dodici venti trenta cento mille primo prima secondo
""".split())

STOPWORDS = {"fr": FR, "it": IT}

LANG_MARKERS = {
    "fr": set("le les des du est une et dans pour qui que sur au aux par avec ce cette son ses sont "
              "ne pas plus leur être été où d l qu".split()),
    "it": set("il gli della delle degli dei del è una e nel nella per che di con sono si non più "
              "alla alle dal dalla questo questa anche come".split()),
}
