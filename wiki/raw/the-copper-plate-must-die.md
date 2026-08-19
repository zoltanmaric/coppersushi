# The Copper Plate Must Die 💀

Source: https://121gigawatts.org/the-copper-plate-must-die/
Published: Tue, 21 Jun 2022 13:51:05 GMT

---

[The Copper Plate Must Die 💀DIE THE COPPER PLATE MUST I think there's an opportunity to make a big step towards reaching zero-emissions in Europe, and it doesn't require any new technologies, but a policy change. This is what I would like to show you today.![The Copper Plate Must Die 💀](https://ssl.gstatic.com/docs/presentations/images/favicon5.ico)Google Docs![The Copper Plate Must Die 💀](https://lh5.googleusercontent.com/-37lPLTIxs5Noo_oo0YNLA1O6qaaEyAMfFPht1Hp_Y3PycaEJKVDMIOudPhx21Xc3C_Fzhp3PCmgTg=w1200-h630-p)](https://docs.google.com/presentation/d/1Bz6dHtJIyGmHMEA9vPFoCKslt9kbPFeVxgBUbtJGAnU/edit?usp=sharing)The argument I present here was originally a talk I gave at [Spark 2022](https://web.archive.org/web/20220426112853/https://www.terrapinn.com/exhibition/spark/agenda.stm) in London on June 22, 2022. You can see the slides from the presentation on the link above.![The Copper Plate Must Die 💀](https://121gigawatts.org/content/images/2022/06/title-slide-2.gif)

I've been pondering. What if getting Europe to zero emissions as soon as possible **--** was **_a problem I had to solve_**? What if I were a benevolent dictator and had all the power to solve this problem? What would I do?

![The Copper Plate Must Die 💀](https://121gigawatts.org/content/images/2022/08/pondering.gif)

\- and I came up with this elaborate plan:

So let's get to it!

## _**What**_ needs to be done

There's pretty much already a consensus in the energy industry on _what_ needs to be done in order to reach zero emissions: we know how to generate electricity without emissions, so let's just

![The Copper Plate Must Die 💀](https://121gigawatts.org/content/images/2022/07/electrify-all-the-things.gif)

Electrifying transport is already well underway, we plan to electrify heating with heat pumps, and then for the rest we plan to use hydrogen, which is also extracted using electricity. If we manage to do that, we will have solved the vast majority of today's emissions, so long as all the electricity comes from zero-emission generation 24/7. There's our "what needs to be done" as a well-defined problem:

## _**How**_ to do it

Figuring out how to generate and deliver zero-emission energy 24/7 is also nothing new. There's plenty of studies about it coming from academia and various think tanks and agencies. They're called **capacity expansion studies**.

These studies look at:

  * Existing and projected regional demand
  * Existing regional renewable generation
  * Existing grid infrastructure
  * Regional solar and wind potentials, based on weather and land suitability



Based on which they estimate:

  * where we should build more renewable generation and storage
  * where we should expand the grid



Such that it costs the least, but still provides renewable energy 24/7 everywhere. 

To do this, they run the data through an optimisation algorithm that may come up with something like this:

The sizes of the pies show how much additional renewable generation or storage we need to install in each region, and the sections of the pie tell us the proportions of the different technologies. For example we see a lot of yellow which is solar along the Mediterranean, and we see a lot of blue along the North and Baltic sea, which is wind, coupled with some pink for hydrogen storage.

The thickness of the links between the pies show the capacities of the transmission grid. If it's grey like here in Spain and in central France, that's the existing grid infrastructure, and if it's coloured brown or green like in Northern France and Germany, that's the required AC or DC transmission expansion.

This particular result is from a study from the Technical University of Berlin, published in March 2022 ([link](https://www.sciencedirect.com/science/article/pii/S0306261922002938)). The study presents best practices for capacity expansion calculations that co-optimise investments in generation, storage, and transmission. This is something I want to stress.

> Capacity expansion is a **co-optimisation** of **generation** , **storage** & **transmission**.

Generation and storage **location** and **capacity _strongly influence_ **how **transmission** should be expanded, and **transmission capacity _strongly influences_ **how **generation** capacity should be expanded and **where it should be placed**.

![The Copper Plate Must Die 💀](https://121gigawatts.org/content/images/2022/08/starsky-and-hutch-ben-stiller.gif)

## Do it

In order to understand how we're doing so far on our path to an optimal zero-emission grid, let me tell you a story of a problem that frequently occurs in Germany.

Say I have a factory in the South of Germany, and I want to buy 20 MW of capacity for tomorrow between 7 and 8 AM. I go to the energy market, and the most competitive sell bid for that time slot happens to come from a wind farm in the North at 20 EUR/MWh. That's a very attractive price, so I give the corresponding buy order, and the trade is executed, meaning I now have a binding agreement to consume at 20 MW for an hour tomorrow at 7, and that wind farm in the north has a binding agreement to produce at 20 MW during the same time.

The forecast for tomorrow says it's going to be very windy in the North, so there's many other wind farms in the North that offer a large volume of energy at very low prices. Conversely, there's many other factories like mine in the South of Germany as that's where industry is concentrated. So now there's a lot of demand in the South matched with a lot of generation in the North. That amounts to tons of gigawatts having to be transferred from North to South through these few transmission lines connecting the North to the South.

The buyers and the sellers on the energy market have to make sure they consume or produce exactly the amounts of energy that they traded, but they don't have to worry about **how** that energy will be delivered to them. That's on the grid operators to worry about.

So the grid operators calculate the power flow according to the dispatch plan, and they see that the highlighted purple line above needs to transfer energy with a throughput of 900 MW, while its capacity is rated at 800 MW, and the other routes are already at capacity. So they perform **redispatch** , which is to say they **curtail** 100 MW of wind in the North, and they call up some gas power plant in the South to deliver the energy closer to where it's consumed.

The **curtailed wind turbines** still get to **keep their payment** , but the **grid operator additionally pays the gas power plant** , and at a premium, since it was dispatched on short notice.

> **UPDATE:** To help me and others get a better intuition of how these kinds of grid congestion work, I've developed [Copper Sushi 🍣](https://121gigawatts.org/copper-sushi-power-flow-european-grid/) \- a pretty, interactive map of the European grid. Go play around with it! 🕹🤓

[Copper Sushi 🍣A Pretty Map of the European Power Grid![The Copper Plate Must Die 💀](https://121gigawatts.org/favicon.png)1.21 GigawattsZoltan Marić![The Copper Plate Must Die 💀](https://121gigawatts.org/content/images/2022/08/coppersushi-gif-1.gif)](https://121gigawatts.org/copper-sushi-power-flow-european-grid/)

Now this is already pretty sad as it is, but the worst part is that it's the market rules that exacerbate this problem. There's no penalty or disincentive that would prevent participants from doing it **again and again**.

**This is by design**.

The idea is that the market shouldn't have to worry about delivering energy as long as both parties are within the same country. They should just be able to trade freely.

> _As if the grid weren 't a grid,_  
> _but a**copper plate**._

No congestion, no bottlenecks. As far as market is concerned, energy can be transferred instantly between any two places on the copper plate.

And the fact that there's nothing stopping the market from repeatedly causing the same problem is not the only issue. If we stick to this rule, new generation will keep disregarding impact on congestion, and make things worse. It will keep getting built far from demand, and demand will keep getting built far from generation. This is my biggest worry.

> _The current market rules_  
> ** _do not incentivise_  
>  _co-optimisation_**  
>  _of generation and transmission._

## Our current path towards zero emissions

I like to imagine our current path towards zero-emissions as shown in the diagram below. The dashed line on the top is where we are today (in 2022), and the dashed line on the bottom is the zero-emission future we want to get to.

If we take co-optimisation seriously, the road to get there might look something like the left side. Generation and transmission influencing each other, growing together more or less straight towards our goal.

Instead, today's market rules are letting **generation** grow more or less randomly, as shown on the right side, and then we say we'll just catch up to new generation with **more grid expansion**.

> _This more expensive, less energy-efficient, and most importantly -**wayyy** slower._

Generation and storage development is mostly performed by the private sector, meaning many **independent parties who move fast**.

**Transmission** , on the other hand, is **built by heavily regulated regional monopolies**. That's not exactly the magic formula to move fast. That means they'll likely always lag significantly behind the development of generation and storage. More reason to co-optimise.

And by the way, that gap that the blue line lags behind the yellow line translates to generation capacity we cannot use in the short run, i.e. **wasted renewable energy** which we'll have to **cover for with old- school power plants**.

## To be fair

![The Copper Plate Must Die 💀](https://121gigawatts.org/content/images/2022/07/Screenshot-2022-06-29-at-16.31.04.png)

The idea of the copper plate comes from a time before renewables, and it's well-intentioned. It's based on the thought that people who live far from power plants shouldn't have to pay more than those who live near. It probably **works well if a grid grows gradually and organically**.

But today we're talking about replacing almost all old- school generation with renewable generation and storage. And we want to do it as fast as possible. That's the **opposite of gradual and organic**. It's a complete overhaul of the grid!

Alright, I think I complained enough. Here's what I'm proposing:

> _In the spot market,**it has to be more expensive to buy energy from "far away" than from "close by"**. _

Yes, in the short term, this may lead to price volatility. But this is exactly the fix that will give the price signal to co-optimise: More generation closer to excess demand areas; more industry, electrolysis and storage near excess generation areas.

The social injustice in the short term caused by potential high prices in some regions can be subsidised by the saved redispatch costs. It makes more sense to subsidise people than to subsidise the band-aiding of technical problems that we're causing ourselves with an outdated market design.

## How do we do that?

The good news is that this already seems to be in consideration. The EU's Agency for the Cooperation of Energy Regulators (ACER) is [considering a reconfiguration of bidding zones](https://twitter.com/eu_acer/status/1524025293916327937). In other words - thinking about how to split up the country-wide copper plates into multiple copper saucers.

> _Following the results of the Locational Marginal Pricing (LMP) analysis carried out by Transmission System Operators (TSOs), the EU Agency for the Cooperation of Energy Regulators (ACER) has initiated the procedure to decide on the TSOs ' proposal of alternative bidding zone configurations. _

National Grid in the UK is conducting a Net Zero Market Reform research, and it's recently [said that they're considering moving to local pricing](https://twitter.com/NationalGridESO/status/1529028988269641728).

> _Moving from a national electricity price to more local pricing will reduce consumer costs and unlock further investment in renewables._

On the other hand, EPEX Spot, the company running the biggest short-term electricity market in Europe, doesn't really like the idea of splitting up into smaller zones. They've outlined their concerns [in a memo in 2016](https://www.epexspot.com/en/news/bidding-zone-split-would-necessitate-considerable-amount-time-and-effort-across-power-trading).

> _Bidding zone split would necessitate considerable amount of time and effort across power trading sector._

I understand that figuring out and implementing the actual solution is a nuanced matter and is anything but simple. I'm not saying that I have a ready solution. I am saying **I want to help work on it**. And I think we need to work on it because **the current market design is broken and it 's leading us astray**.

Feel free to comment on this post on [Twitter](https://twitter.com/zoltanmaric/status/1541276747429208070) or on [LinkedIn](https://www.linkedin.com/posts/zoltanmaric_the-copper-plate-must-die-activity-6947042418194083840-qZ4F?utm_source=linkedin_share&utm_medium=member_desktop_web) 🙌
