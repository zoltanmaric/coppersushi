# Copper Sushi 🍣

Source: https://121gigawatts.org/copper-sushi-power-flow-european-grid/
Published: Fri, 19 Aug 2022 18:45:00 GMT

---

## A Pretty Visualisation of the European Power Grid

![Copper Sushi 🍣](https://121gigawatts.org/content/images/2022/08/coppersushi-gif-1.gif)

This is a map of the European electrical transmission network. Each dot is a connection point where all the consumption from nearby settlements connects to the network, as well as all electricity generation from nearby power plants.

  * 🥒 Green dots mean more generation than consumption, so they **export power to** the network
  * 🍇 Purple dots mean more consumption than generation, so they **take power from** the network
  * ▲ Triangles show **which way** the power is flowing
  * 🕹 Hovering over the triangles shows **how much power is flowing** through the power lines, and each line's **total capacity**



The numbers shown above are the results of running an optimisation algorithm. Its aim is to find **optimal power flow**. It goes like this:

I pick a date, and I ask the algorithm to calculate:

  * which power plants should produce how much power
  * for each 2-hour slot in that day,
  * so that the total cost is minimal,
  * and all power consumption is covered



To do that, for each connection point and each time slot, the algorithm gathers all the inputs first:

  * 💻💡 Get **total consumption** from the nearby settlements and industry
  * 💶 Get the **price of generation** per MW for solar, wind, hydro, coal, oil, gas & nuclear
  * 🏭 Get the **total generation capacity** available at each point for the **old-school power plants** (gas, coal, nuclear, etc.)
  * ☀️💨 Calculate how much the **sun** is shining, the **wind** is blowing, and the **rivers** are flowing (from historical data for the date I picked), based on which it can
  * ⚡️Calculate **how much solar, wind and hydro power plants can generate** at most
  * 🔌 Get **how much power each power line can transfer** at most



And then it just starts guessing how much each power plant should produce, while making sure that all of the above adds up right. It keeps guessing and improving its guesses until it finds the minimum cost of generation that satisfies all of these conditions.

If you then **add up all the power generated** at each point, and **subtract all the power consumed** at each point, you get the numbers which pop up if you hover over the dots.

## Where'd You Get the Data? 🥸

The data comes from `pypsa-eur`, a research paper which is to my knowledge the best summary of the European power grid data that is currently publicly available:

[GitHub - PyPSA/pypsa-eur: PyPSA-Eur: An Open Optimisation Model of the European Transmission SystemPyPSA-Eur: An Open Optimisation Model of the European Transmission System - GitHub - PyPSA/pypsa-eur: PyPSA-Eur: An Open Optimisation Model of the European Transmission System![Copper Sushi 🍣](https://github.com/fluidicon.png)GitHubPyPSA![Copper Sushi 🍣](https://opengraph.githubassets.com/129b79416a66cc263f49af180ce6e1a6345f1784b3c239829b978f2c27601bf2/PyPSA/pypsa-eur)](https://github.com/PyPSA/pypsa-eur)

A huge thanks to [Fabian Neumann](https://twitter.com/fneum_) and everyone else from Professor [Tom Brown](https://twitter.com/nworbmot)'s research group behind `pypsa-eur` \- for the great software, great documentation, and for gathering and prepaing all the data.

The little bit of code that I had to write on top of `pypsa-eur` to make that pretty-ass map above can be found here:

[GitHub - zoltanmaric/coppersushi: Optimal power flow visualisation based on pypsa-eurOptimal power flow visualisation based on pypsa-eur - GitHub - zoltanmaric/coppersushi: Optimal power flow visualisation based on pypsa-eur![Copper Sushi 🍣](https://github.com/fluidicon.png)GitHubzoltanmaric![Copper Sushi 🍣](https://opengraph.githubassets.com/388df45b4eb4ed80ec56c20ce612b3bb979f10b3db83a08803eed4aa03600ba5/zoltanmaric/coppersushi)](https://github.com/zoltanmaric/coppersushi)

## Is This Real? 🦦

The math behind it is real, and it uses the same calculations that real grid operators use to keep the lights on. However, the amount of power that each power plant actually produces depends on the price they offer. This price varies wildly from hour to hour, and neither the price nor the power amount is publicly available.

Instead, `pypsa-eur` makes assumptions on prices for solar, wind, coal, nuclear, etc. based on historical averages, and then runs an optimisation algorithm to cover all consumption for the least cost of production. In short:

> It's **the real way of calculating who produces how much** , and **how the power flows** in that case;  
> but it's calculated based on **data that is not real**.

For a full discussion of the limitations of the model, have a look at chapter 4 of the original `pypsa-eur` paper:

[PyPSA-Eur: An Open Optimisation Model of the European Transmission SystemPyPSA-Eur, the first open model dataset of the European power system at thetransmission network level to cover the full ENTSO-E area, is presented. Itcontains 6001 lines (alternating current lines at and above 220 kV voltagelevel and all high voltage direct current lines), 3657 substations, a new…![Copper Sushi 🍣](https://static.arxiv.org/static/browse/0.3.4/images/icons/favicon.ico)arXiv.orgJonas Horsch![Copper Sushi 🍣](https://static.arxiv.org/icons/twitter/arxiv-logo-twitter-square.png)](https://arxiv.org/abs/1806.01613)

## Why Does This Matter? 🤷‍♀️

**TL;DR:** we can delete most of the emissions of the developed world today by switching heating & car and truck transport to electrical - if we make sure we generate all electricity with near-zero emissions. Just building more renewable generation won't solve it though, as you still need to make sure it covers all consumption **everywhere**. This map intends to show why that's a complicated problem, and why we should also be smart about **where** we build renewable generation so that most of the generated energy can also be **used** and not **thrown away** because the grid can't handle it.

I wrote a less condensed explanation of this problem in another post:

[The Copper Plate Must Die 💀EU energy market rules are counterproductive to grid congestion & don't incentivise optimal use of renewables.![Copper Sushi 🍣](https://121gigawatts.org/favicon.png)1.21 GigawattsZoltan Marić![Copper Sushi 🍣](https://121gigawatts.org/content/images/2022/06/title-slide-2.gif)](https://121gigawatts.org/the-copper-plate-must-die/)

## 👋
